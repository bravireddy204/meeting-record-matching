"""Small local REST API using the Python standard library."""
import argparse
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from .pipeline import run,DEFAULT_DATA


def make_handler(result):
    class Handler(BaseHTTPRequestHandler):
        def respond(self,status,payload):
            body=json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url=urlsplit(self.path)
            query=parse_qs(url.query)
            if url.path=='/health':
                return self.respond(200,{'status':'ok','counts':result['counts']})
            if url.path=='/duplicates':
                return self.respond(200,result['duplicate_candidates'])
            if url.path=='/matches':
                record=query.get('crm_id',[None])[0]
                if record and not any(p['crm_id']==record for p in result['predictions']):
                    return self.respond(404,{'error':'Unknown CRM ID'})
                return self.respond(200,[p for p in result['predictions'] if p['match'] and (record is None or p['crm_id']==record)])
            if url.path=='/predict':
                a,b=query.get('crm_id',[None])[0],query.get('calendar_id',[None])[0]
                if not a or not b:
                    return self.respond(400,{'error':'crm_id and calendar_id are required'})
                prediction=next((p for p in result['predictions'] if p['crm_id']==a and p['calendar_id']==b),None)
                return self.respond(200,prediction) if prediction else self.respond(404,{'error':'Unknown record ID'})
            return self.respond(404,{'error':'Unknown endpoint'})
    return Handler


def main():
    parser=argparse.ArgumentParser(description='Serve predictions for records in the configured input files')
    parser.add_argument('--data-dir',default=str(DEFAULT_DATA))
    parser.add_argument('--timezone',default='America/New_York')
    parser.add_argument('--threshold',type=float,default=.68)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    result=run(args.data_dir,args.timezone,args.threshold)
    server=ThreadingHTTPServer((args.host,args.port),make_handler(result))
    print(f'API listening on http://{args.host}:{args.port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__=='__main__':
    main()
