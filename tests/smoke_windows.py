"""Probe actual source UI and its regular acknowledged shutdown, no model calls."""
from pathlib import Path
from datetime import datetime,timezone
import http.client,json,os,re,subprocess,sys,tempfile,time
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='Source UI ') as temp:
 trace=Path(temp)/'trace.log'
 with trace.open('w',encoding='utf-8') as output:
  process=subprocess.Popen([sys.executable,'-X','utf8','-B',str(ROOT/'src/local_app.py'),'--no-browser','--port','0','--data-dir',str(Path(temp)/'Private data')],cwd=temp,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
 try:
  deadline=time.monotonic()+30
  address=None
  while time.monotonic()<deadline:
   match=re.search(r'Lokale Oberfläche: (http://127\.0\.0\.1:\d+/#[^\s]+)',trace.read_text(encoding='utf-8',errors='replace'))
   if match:address=urlsplit(match.group(1));break
   if process.poll() is not None:raise AssertionError('Source app ended before readiness')
   time.sleep(.1)
  if address is None:raise AssertionError('No ready source UI')
  def api(path,value=None,authenticated=True):
   conn=http.client.HTTPConnection(address.hostname,address.port,timeout=10)
   headers={'X-App-Token':address.fragment} if authenticated else {}
   if value is not None:headers['Content-Type']='application/json'
   try:
    conn.request('POST' if value is not None else 'GET',path,json.dumps(value) if value is not None else None,headers)
    response=conn.getresponse();data=response.read();assert response.status==200,(path,response.status)
    return data
   finally:conn.close()
  assert b'prompt-dialog' in api('/',authenticated=False)
  assert isinstance(json.loads(api('/api/state')),dict)
  api('/api/shutdown',{'mode':'idle'})
  deadline=time.monotonic()+20
  while time.monotonic()<deadline:
   if json.loads(api('/api/runtime'))['state']=='closed':break
   time.sleep(.05)
  else:raise AssertionError('Regular shutdown not acknowledged')
  assert process.wait(timeout=25)==0
 finally:
  if process.poll() is None:process.terminate();process.wait(timeout=10)
print('PASS source UI startup, authenticated state, graceful shutdown and temporary data cleanup')
