"""Local HTTP boundary; validates public query fields and never executes generated code."""
import json
from http.server import BaseHTTPRequestHandler,HTTPServer
from .retrieve import ask,validate_citation

def make_handler(index,mode='scoped',page_budget=4,char_budget=6000):
 class Handler(BaseHTTPRequestHandler):
  def reply(self,status,obj):
   body=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def do_GET(self):
   if self.path=='/health':self.reply(200,{'status':'ready','backend':'local_page_bm25','pageindex_api_called':False})
   else:self.reply(404,{'error':'unknown_path'})
  def do_POST(self):
   try:size=int(self.headers.get('Content-Length','0'))
   except ValueError:self.reply(400,{'error':'invalid_content_length'});return
   if size<0:self.reply(400,{'error':'invalid_content_length'});return
   if size>30000:self.reply(413,{'error':'request_too_large'});return
   try:
    payload=json.loads(self.rfile.read(size))
    if self.path=='/ask':result=ask(index,payload,mode,page_budget,char_budget)
    elif self.path=='/validate-citation':
     if not isinstance(payload,dict) or set(payload)!={'citation'} or not isinstance(payload['citation'],dict):raise ValueError('only citation is accepted')
     result=validate_citation(payload['citation'],index)|{'semantic_review_required':True,'entailment_verified':False}
    else:self.reply(404,{'error':'unknown_path'});return
    self.reply(200,result)
   except (ValueError,TypeError,KeyError) as e:self.reply(400,{'error':type(e).__name__,'detail':str(e)[:240]})
  def log_message(self,*args):pass
 return Handler

def serve(index,host='127.0.0.1',port=8765,mode='scoped',page_budget=4,char_budget=6000):
 server=HTTPServer((host,port),make_handler(index,mode,page_budget,char_budget));print(f'local evidence service http://{host}:{server.server_port}',flush=True);server.serve_forever()
