# tktk cloud skill

This repository includes the original `tktk` v0.14.0 skill supplied by its owner:

```text
.agents/skills/tktk/SKILL.md
.agents/skills/tktk/agents/openai.yaml
.agents/skills/tktk/assets/
.agents/skills/tktk/references/
.agents/skills/tktk/scripts/
```

All 16 skill files are preserved from the original export. No additional plugin,
MCP server, image API key, package installation, or background service is required
by this repository. Image tasks require the host's built-in image generation tool.

## Use in Codex Cloud

1. Include this repository in the cloud environment.
2. Save and publish (or republish) the environment after it has prepared this
   repository. The install script and start skill may remain unset: there are no
   dependencies or services to start for skill discovery.
3. Start a new cloud task using that environment.
4. Check whether `tktk` appears in the available skills or skill mention menu.
   Verify loading with `$tktk Explain your capabilities without generating images`.
5. Supply product photos and the requested task when ready to generate assets.

Repository skills are available to cloud tasks; personal skills on a local
computer are not automatically synced. Each new task uses the published
environment's prepared filesystem, while an existing task retains its own state.
This setup covers environments that include this repository. It does not install
an account-wide skill into unrelated environments.

Repository layout alone does not prove that a particular cloud task or menu has
loaded the skill. Check a new task after publishing; if discovery fails, report
the available skills and any loading errors before claiming success.

Official references:

- https://learn.chatgpt.com/docs/environments/cloud-environments
- https://learn.chatgpt.com/docs/build-skills
