(async function dispatchBatch(batch, host) {
  // Evaluate in functions.exec. Only the injected host calls built-in imagegen.
  const q = value => "'" + String(value).replace(/'/g, "''") + "'";
  const clock = host.now || (() => new Date().toISOString());
  const write = host.write || (() => {});
  const pending = new Set(), seen = new Set(), outcomes = [];
  let stopped = false, receipts = Promise.resolve();
  async function claim() {
    if (host.claim) return await host.claim();
    const cmd = '& ' + q(batch.python_executable) + ' -B -X utf8 ' +
      q(batch.queue_script) + ' --task-dir ' + q(batch.task_dir) +
      ' claim --auto-refill --limit 3 --pending-limit ' + batch.pending_limit;
    const response = await host.execCommand({cmd, max_output_tokens: 16000});
    if (response.exit_code !== 0) throw Error(response.output);
    return JSON.parse(response.output);
  }
  async function receive(item, result, returned_at) {
    if (host.receive) return await host.receive({...item, result, returned_at});
    const path = String(result.output_hint || '').match(/as ([^\r\n]+?\.png) by default/);
    if (!path) throw Error('Result has no recognized local path; recover output without regeneration');
    const cmd = '& ' + q(batch.python_executable) + ' -B -X utf8 ' + q(batch.handoff_script) +
      ' --task-dir ' + q(batch.task_dir) + ' receive --job-id ' + q(item.job.id) +
      ' --source ' + q(path[1]) + ' --submitted-at ' + q(item.submitted_at) + ' --returned-at ' + q(returned_at);
    const response = await host.execCommand({cmd, max_output_tokens: 1400});
    if (response.exit_code !== 0) throw Error(response.output);
    return JSON.parse(response.output);
  }
  function launch(jobs) {
    // Start EVERY call in this batch before awaiting receipt, claim, or yield.
    const identifiers = jobs.map(job => job.id);
    if (new Set(identifiers).size !== identifiers.length || identifiers.some(id => seen.has(id)))
      throw Error('Duplicate dispatch id; reconcile without resubmitting');
    const calls = jobs.map(job => {
      seen.add(job.id);
      const submitted_at = clock();
      let request;
      try { request = Promise.resolve(host.imagegen({prompt: job.prompt,
        referenced_image_paths: job.referenced_image_paths, transparent_background: false})); }
      catch (error) { request = Promise.reject(error); }
      return {job, submitted_at, request};
    });
    for (const item of calls) {
      let task;
      task = complete(item).then(value => outcomes.push({status: 'fulfilled', value}),
        error => {stopped = true; outcomes.push({status: 'rejected', reason: String(error)});})
        .finally(() => pending.delete(task));
      pending.add(task);
    }
  }
  async function complete(item) {
    let result;
    try { result = await item.request; }
    catch (error) {
      stopped = true;
      write({id: item.job.id, stage: 'generation', error: String(error),
        action: 'Automatic refill stopped. Reconcile explicit error; preserve other in-flight calls.'});
      return {id: item.job.id, status: 'generation_error'};
    }
    const returned_at = clock();
    // Serialize queue mutations within this runner; never hold a lock during generation.
    const operation = receipts.then(async () => {
      let receipt;
      try { receipt = await receive(item, result, returned_at); }
      catch (error) {
        stopped = true;
        host.emit(result);
        write({id: item.job.id, stage: 'receipt', error: String(error),
          output_hint: result.output_hint || null, submitted_at: item.submitted_at, returned_at,
          action: 'Image already returned. Recover its file; do not regenerate.'});
        return {id: item.job.id, status: 'receipt_error'};
      }
      host.emit(result);
      write({id: item.job.id, status: 'generated_pending_review', saved_image: receipt.saved_image,
        submitted_at: item.submitted_at, returned_at});
      if (batch.auto_refill && !stopped) {
        try {
          const next = await claim();
          if (!stopped) launch(next.jobs);
          else if (next.jobs.length) write({stage: 'reserved_not_started', ids: next.jobs.map(j => j.id),
            action: 'An error arrived during claim. These reservations were not submitted; reconcile explicitly.'});
        } catch (error) {
          stopped = true;
          write({stage: 'refill', error: String(error),
            action: 'Inspect dispatch records before recovery; do not blindly claim again.'});
        }
      }
      return {id: item.job.id, status: 'generated_pending_review'};
    });
    receipts = operation.catch(() => {});
    const value = await operation;
    if (host.yieldControl) await host.yieldControl();
    return value;
  }
  launch(batch.jobs);
  if (host.yieldControl) await host.yieldControl();
  // Include newly refilled calls; outer await keeps every promise alive.
  while (pending.size) await Promise.race(pending);
  return outcomes;
})
