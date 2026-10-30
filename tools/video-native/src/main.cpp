#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <commdlg.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mferror.h>
#include <wrl/client.h>
#include <bcrypt.h>
#include <string>
#include <vector>
#include <thread>
#include <sstream>
#include <iomanip>
#include <filesystem>
#include <fstream>
#include <algorithm>
using Microsoft::WRL::ComPtr;
static HWND win, inp, outp, mark, secret, status, runbtn, compareInput;
static std::wstring value(HWND h){int n=GetWindowTextLengthW(h);std::vector<wchar_t> s(n+1);GetWindowTextW(h,s.data(),n+1);return s.data();}
static HWND control(const wchar_t* cls,const wchar_t* txt,DWORD style,int x,int y,int w,int h,int id=0){return CreateWindowExW(0,cls,txt,WS_CHILD|WS_VISIBLE|style,x,y,w,h,win,(HMENU)(INT_PTR)id,GetModuleHandleW(nullptr),nullptr);}
static unsigned long long next(unsigned long long& x){x^=x>>12;x^=x<<25;x^=x>>27;return x*2685821657736338717ull;}
static unsigned long long seedFor(const std::wstring& s){unsigned long long h=14695981039346656037ull;for(auto c:s){h^=(unsigned short)c;h*=1099511628211ull;}return h;}
static void embed(BYTE* p,DWORD used,UINT32 w,UINT32 h,const std::wstring& payload){if(w<96||h<96||used<(size_t)w*h*4||payload.empty())return;auto s=seedFor(payload);for(int i=0;i<96;i++){auto r=next(s);auto x=24+(unsigned)(r%(w-48)),y=24+(unsigned)((r>>32)%(h-48));int d=(r&1)?2:-2;for(int yy=-3;yy<=3;yy++)for(int xx=-3;xx<=3;xx++){BYTE* z=p+((size_t)(y+yy)*w+x+xx)*4;for(int k=0;k<3;k++){int n=int(z[k])+d;z[k]=(BYTE)(n<0?0:n>255?255:n);}}}}
static std::wstring md5(const std::wstring& file){HANDLE f=CreateFileW(file.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);if(f==INVALID_HANDLE_VALUE)return L"error";BCRYPT_ALG_HANDLE a=nullptr;BCRYPT_HASH_HANDLE b=nullptr;std::wstring result=L"error";DWORD sz=0,got=0;if(BCryptOpenAlgorithmProvider(&a,BCRYPT_MD5_ALGORITHM,nullptr,0)==0&&BCryptGetProperty(a,BCRYPT_OBJECT_LENGTH,(PUCHAR)&sz,sizeof(sz),&got,0)==0){std::vector<BYTE> obj(sz);BYTE digest[16]{};if(BCryptCreateHash(a,&b,obj.data(),sz,nullptr,0,0)==0){BYTE buf[65536];DWORD n;bool ok=true;while(ReadFile(f,buf,sizeof(buf),&n,nullptr)&&n){if(BCryptHashData(b,buf,n,0)!=0){ok=false;break;}}if(ok&&BCryptFinishHash(b,digest,16,0)==0){std::wostringstream os;for(auto c:digest)os<<std::hex<<std::setfill(L'0')<<std::setw(2)<<(int)c;result=os.str();}}}if(b)BCryptDestroyHash(b);if(a)BCryptCloseAlgorithmProvider(a,0);CloseHandle(f);return result;}
static HRESULT process(const std::wstring& input,const std::wstring& output,const std::wstring& payload){HRESULT hr=CoInitializeEx(nullptr,COINIT_MULTITHREADED);if(FAILED(hr))return hr;hr=MFStartup(MF_VERSION);if(FAILED(hr)){CoUninitialize();return hr;}do{ComPtr<IMFSourceReader> reader;hr=MFCreateSourceReaderFromURL(input.c_str(),nullptr,&reader);if(FAILED(hr))break;hr=reader->SetStreamSelection(MF_SOURCE_READER_ALL_STREAMS,FALSE);if(FAILED(hr))break;hr=reader->SetStreamSelection(MF_SOURCE_READER_FIRST_VIDEO_STREAM,TRUE);if(FAILED(hr))break;ComPtr<IMFMediaType> inType;hr=MFCreateMediaType(&inType);if(FAILED(hr))break;inType->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video);inType->SetGUID(MF_MT_SUBTYPE,MFVideoFormat_RGB32);hr=reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,nullptr,inType.Get());if(FAILED(hr))break;hr=reader->GetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,&inType);if(FAILED(hr))break;UINT32 w=0,h=0;hr=MFGetAttributeSize(inType.Get(),MF_MT_FRAME_SIZE,&w,&h);if(FAILED(hr))break;ComPtr<IMFSinkWriter> writer;hr=MFCreateSinkWriterFromURL(output.c_str(),nullptr,nullptr,&writer);if(FAILED(hr))break;ComPtr<IMFMediaType> dest;hr=MFCreateMediaType(&dest);if(FAILED(hr))break;dest->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video);dest->SetGUID(MF_MT_SUBTYPE,MFVideoFormat_H264);dest->SetUINT32(MF_MT_AVG_BITRATE,5000000);dest->SetUINT32(MF_MT_INTERLACE_MODE,MFVideoInterlace_Progressive);MFSetAttributeSize(dest.Get(),MF_MT_FRAME_SIZE,w,h);UINT32 fn=30,fd=1;MFGetAttributeRatio(inType.Get(),MF_MT_FRAME_RATE,&fn,&fd);MFSetAttributeRatio(dest.Get(),MF_MT_FRAME_RATE,fn,fd);MFSetAttributeRatio(dest.Get(),MF_MT_PIXEL_ASPECT_RATIO,1,1);DWORD stream=0;hr=writer->AddStream(dest.Get(),&stream);if(FAILED(hr))break;hr=writer->SetInputMediaType(stream,inType.Get(),nullptr);if(FAILED(hr))break;hr=writer->BeginWriting();if(FAILED(hr))break;while(true){DWORD index=0,flags=0;LONGLONG ts=0;ComPtr<IMFSample> sample;hr=reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,&index,&flags,&ts,&sample);if(FAILED(hr))break;if(flags&MF_SOURCE_READERF_ENDOFSTREAM)break;if(!sample)continue;if(!payload.empty()){ComPtr<IMFMediaBuffer> buffer;hr=sample->ConvertToContiguousBuffer(&buffer);if(FAILED(hr))break;BYTE* p=nullptr;DWORD maxlen=0,used=0;hr=buffer->Lock(&p,&maxlen,&used);if(FAILED(hr))break;embed(p,used,w,h,payload);buffer->Unlock();}hr=writer->WriteSample(stream,sample.Get());if(FAILED(hr))break;}if(SUCCEEDED(hr))hr=writer->Finalize();}while(false);MFShutdown();CoUninitialize();return hr;}


static unsigned long long be32(const unsigned char* p){return (unsigned long long(p[0])<<24)|(unsigned long long(p[1])<<16)|(unsigned long long(p[2])<<8)|p[3];}
static std::wstring detectC2PA(const std::wstring& path){
 std::ifstream f(std::filesystem::path(path),std::ios::binary|std::ios::ate);
 if(!f)return L"C2PA: cannot open input";
 unsigned long long size=(unsigned long long)f.tellg(),pos=0;
 const unsigned char id[16]={0xd8,0xfe,0xc3,0xd6,0x1b,0x0e,0x48,0x3c,0x92,0x97,0x58,0x28,0x87,0x7e,0xc4,0x81};
 while(pos+8<=size){unsigned char h[32]={};f.seekg((std::streamoff)pos);f.read((char*)h,8);if(!f)break;
 unsigned long long n=be32(h);unsigned header=8;
 if(n==1){f.read((char*)h+8,8);if(!f)break;n=(be32(h+8)<<32)|be32(h+12);header=16;}
 else if(n==0)n=size-pos;
 if(n<header||n>size-pos)break;
 if(h[4]=='u'&&h[5]=='u'&&h[6]=='i'&&h[7]=='d'&&n>=header+16){
 f.read((char*)h+header,16);if(f&&memcmp(h+header,id,16)==0)return L"C2PA: embedded BMFF UUID box FOUND (signature not validated).";
 }
 pos+=n;
 }
 return L"C2PA: no top-level C2PA UUID box found. Does NOT prove absence of credentials.";
}
static std::wstring batchFolder(const std::wstring& example,const std::wstring& outDir,const std::wstring& mark){
 namespace fs=std::filesystem;fs::path folder=fs::path(example).parent_path(),dest(outDir);
 if(folder.empty()||!fs::is_directory(folder))return L"Batch: choose a sample input video from a folder.";
 std::error_code ec;fs::create_directories(dest,ec);if(ec)return L"Batch: output directory unavailable.";
 int ok=0,fail=0;
 for(auto const& entry:fs::directory_iterator(folder,ec)){
 if(!entry.is_regular_file())continue;auto ext=entry.path().extension().wstring();
 std::transform(ext.begin(),ext.end(),ext.begin(),::towlower);if(ext!=L".mp4")continue;
 fs::path output=dest/(entry.path().stem().wstring()+L"_v1.mp4");
 if(fs::equivalent(entry.path(),output,ec)){ec.clear();continue;}ec.clear();
 HRESULT hr=process(entry.path().wstring(),output.wstring(),mark);if(SUCCEEDED(hr))ok++;else fail++;
 }
 return L"Batch completed: "+std::to_wstring(ok)+L" succeeded, "+std::to_wstring(fail)+L" failed. Audio preservation is best-effort.";
}

static unsigned long long frameDhash(const BYTE* p,DWORD len,UINT32 w,UINT32 h){
 if(w<10||h<8||((unsigned long long)w*h*4)>len)return 0;
 unsigned long long bits=0;
 for(int y=0;y<8;y++)for(int x=0;x<8;x++){
  auto luminance=[&](int px)->int{int xx=(px*(int)(w-1))/8;int yy=(y*(int)(h-1))/7;const BYTE* q=p+((size_t)yy*w+xx)*4;return (int(q[0])*11+int(q[1])*59+int(q[2])*30)/100;};
  bits=(bits<<1)|(luminance(x)>luminance(x+1)?1ull:0ull);
 }
 return bits;
}
static HRESULT fingerprint(const std::wstring& file,std::vector<unsigned long long>& fp){
 HRESULT hr=CoInitializeEx(nullptr,COINIT_MULTITHREADED);if(FAILED(hr))return hr;
 hr=MFStartup(MF_VERSION);if(FAILED(hr)){CoUninitialize();return hr;}
 do{
  ComPtr<IMFSourceReader> r;hr=MFCreateSourceReaderFromURL(file.c_str(),nullptr,&r);if(FAILED(hr))break;
  r->SetStreamSelection(MF_SOURCE_READER_ALL_STREAMS,FALSE);r->SetStreamSelection(MF_SOURCE_READER_FIRST_VIDEO_STREAM,TRUE);
  ComPtr<IMFMediaType> t;hr=MFCreateMediaType(&t);if(FAILED(hr))break;
  t->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video);t->SetGUID(MF_MT_SUBTYPE,MFVideoFormat_RGB32);
  hr=r->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,nullptr,t.Get());if(FAILED(hr))break;
  hr=r->GetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,&t);if(FAILED(hr))break;
  UINT32 w=0,h=0;hr=MFGetAttributeSize(t.Get(),MF_MT_FRAME_SIZE,&w,&h);if(FAILED(hr))break;
  DWORD frames=0;while(frames<1800&&fp.size()<12){
   DWORD si=0,flags=0;LONGLONG ts=0;ComPtr<IMFSample> sample;
   hr=r->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,&si,&flags,&ts,&sample);if(FAILED(hr))break;
   if(flags&MF_SOURCE_READERF_ENDOFSTREAM)break;
   if(sample&&frames%30==0){ComPtr<IMFMediaBuffer> b;hr=sample->ConvertToContiguousBuffer(&b);if(FAILED(hr))break;
    BYTE* p=nullptr;DWORD cap=0,len=0;hr=b->Lock(&p,&cap,&len);if(FAILED(hr))break;
    fp.push_back(frameDhash(p,len,w,h));b->Unlock();
   }
   ++frames;
  }
 }while(false);
 MFShutdown();CoUninitialize();return hr;
}
static unsigned bitcount(unsigned long long a){unsigned n=0;while(a){a&=a-1;n++;}return n;}
static std::wstring compareVideos(const std::wstring& a,const std::wstring& b){
 std::vector<unsigned long long> x,y;HRESULT ha=fingerprint(a,x),hb=fingerprint(b,y);
 if(FAILED(ha)||FAILED(hb)||x.empty()||y.empty())return L"Could not extract video fingerprints (codec or file unsupported).";
 size_t n=(x.size()<y.size()?x.size():y.size());unsigned total=0;
 for(size_t i=0;i<n;i++)total+=bitcount(x[i]^y[i]);
 double similarity=100.0*(1.0-double(total)/double(n*64));
 std::wostringstream o;o<<L"Visual dHash similarity: "<<std::fixed<<std::setprecision(1)<<similarity
 <<L"% ("<<n<<L" sampled frames). Approximate only; not a platform duplicate score.";
 return o.str();
}

static void pick(HWND field,bool save){wchar_t path[MAX_PATH]={};OPENFILENAMEW ofn={};ofn.lStructSize=sizeof(ofn);ofn.hwndOwner=win;ofn.lpstrFile=path;ofn.nMaxFile=MAX_PATH;ofn.lpstrFilter=L"MP4 Files\0*.mp4\0All Files\0*.*\0";ofn.Flags=OFN_PATHMUSTEXIST|(save?OFN_OVERWRITEPROMPT:OFN_FILEMUSTEXIST);ofn.lpstrDefExt=L"mp4";if((save?GetSaveFileNameW(&ofn):GetOpenFileNameW(&ofn)))SetWindowTextW(field,path);}
static LRESULT CALLBACK wndproc(HWND h,UINT msg,WPARAM wp,LPARAM lp){switch(msg){case WM_CREATE:win=h;control(L"STATIC",L"Input MP4",0,20,15,100,20);inp=control(L"EDIT",L"",WS_BORDER|ES_AUTOHSCROLL,20,38,480,27);control(L"BUTTON",L"Browse",0,510,38,85,27,1);control(L"STATIC",L"Output MP4",0,20,78,100,20);outp=control(L"EDIT",L"",WS_BORDER|ES_AUTOHSCROLL,20,100,480,27);control(L"BUTTON",L"Browse",0,510,100,85,27,2);control(L"STATIC",L"Invisible mark text (experimental)",0,20,140,300,22);mark=control(L"EDIT",L"MYBRAND-2026",WS_BORDER|ES_AUTOHSCROLL,20,165,575,28);control(L"STATIC",L"Watermark key",0,20,205,250,22);secret=control(L"EDIT",L"",WS_BORDER|ES_PASSWORD|ES_AUTOHSCROLL,20,230,575,28);runbtn=control(L"BUTTON",L"Process Video",BS_DEFPUSHBUTTON,20,276,575,34,3);
control(L"STATIC",L"Compare with another video (visual duplicate detection)",0,20,317,500,22);
compareInput=control(L"EDIT",L"",WS_BORDER|ES_AUTOHSCROLL,20,341,460,27);
control(L"BUTTON",L"Browse",0,488,341,105,27,4);
control(L"BUTTON",L"Compare visual fingerprints",0,20,377,575,32,5);
control(L"BUTTON",L"Check C2PA",0,20,416,275,29,6);
control(L"BUTTON",L"Batch input folder",0,307,416,288,29,7);
status=control(L"EDIT",L"V1.1 - native C++: C2PA box check, batch, audio best effort.",WS_BORDER|ES_MULTILINE|ES_READONLY,20,458,575,73);return 0;case WM_COMMAND:if(LOWORD(wp)==1){pick(inp,false);return 0;}if(LOWORD(wp)==2){pick(outp,true);return 0;}if(LOWORD(wp)==4){pick(compareInput,false);return 0;}if(LOWORD(wp)==5){auto a=value(inp),b=value(compareInput);if(a.empty()||b.empty()){MessageBoxW(h,L"Choose two input videos",L"Missing files",MB_OK);return 0;}SetWindowTextW(status,L"Comparing visual fingerprints...");std::thread([h,a,b](){auto result=compareVideos(a,b);PostMessageW(h,WM_APP+1,0,(LPARAM)new std::wstring(result));}).detach();return 0;}if(LOWORD(wp)==6){auto a=value(inp);SetWindowTextW(status,detectC2PA(a).c_str());return 0;}
if(LOWORD(wp)==7){auto a=value(inp),b=value(outp),c=value(mark)+L"|"+value(secret);if(a.empty()||b.empty()){MessageBoxW(h,L"Select an example source MP4 and output path. Batch outputs to output file's parent directory.",L"Batch",MB_OK);return 0;}EnableWindow(runbtn,FALSE);SetWindowTextW(status,L"Batch running...");auto folder=std::filesystem::path(b).parent_path().wstring();std::thread([h,a,folder,c](){auto report=batchFolder(a,folder,c);PostMessageW(h,WM_APP+1,0,(LPARAM)new std::wstring(report));}).detach();return 0;}if(LOWORD(wp)==3){auto a=value(inp),b=value(outp),c=value(mark)+L"|"+value(secret);if(a.empty()||b.empty()||a==b){MessageBoxW(h,L"Select different input and output paths",L"Error",MB_OK);return 0;}EnableWindow(runbtn,FALSE);SetWindowTextW(status,L"Processing...");std::thread([h,a,b,c](){HRESULT hr=process(a,b,c);std::wstring result;if(SUCCEEDED(hr))result=L"Finished. MD5: "+md5(b);else{wchar_t tmp[60];swprintf_s(tmp,L"Failed: 0x%08X",(unsigned)hr);result=tmp;}PostMessageW(h,WM_APP+1,0,(LPARAM)new std::wstring(result));}).detach();return 0;}break;case WM_APP+1:{auto p=(std::wstring*)lp;SetWindowTextW(status,p->c_str());delete p;EnableWindow(runbtn,TRUE);return 0;}case WM_DESTROY:PostQuitMessage(0);return 0;}return DefWindowProcW(h,msg,wp,lp);}
int WINAPI wWinMain(HINSTANCE hi,HINSTANCE,LPWSTR,int show){CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);WNDCLASSEXW wc={sizeof(wc)};wc.lpfnWndProc=wndproc;wc.hInstance=hi;wc.lpszClassName=L"VideoNativeTool";wc.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);wc.hCursor=LoadCursorW(nullptr,IDC_ARROW);RegisterClassExW(&wc);auto h=CreateWindowExW(0,wc.lpszClassName,L"VideoNative Win11 x64",WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX,CW_USEDEFAULT,CW_USEDEFAULT,640,585,nullptr,nullptr,hi,nullptr);ShowWindow(h,show);MSG m;while(GetMessageW(&m,nullptr,0,0)){TranslateMessage(&m);DispatchMessageW(&m);}CoUninitialize();return 0;}
