import argparse
import json
from pathlib import Path
from .pipeline import run,DEFAULT_DATA
from .evaluate import evaluate


def main():
    parser=argparse.ArgumentParser(description='Run meeting matching and labeled evaluation')
    parser.add_argument('--data-dir',type=Path,default=DEFAULT_DATA)
    parser.add_argument('--output-dir',type=Path,default=Path('outputs'))
    parser.add_argument('--timezone',default='America/New_York')
    parser.add_argument('--threshold',type=float,default=.68)
    args=parser.parse_args()
    result=run(args.data_dir,args.timezone,args.threshold)
    labels=json.loads((args.data_dir/'evaluation_labels.json').read_text(encoding='utf-8'))
    evaluation=evaluate(result,labels)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for name,value in [('predictions',result),('evaluation',evaluation)]:
        (args.output_dir/f'{name}.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'counts':result['counts'],'cross_source':evaluation['cross_source'],'duplicate_detection':evaluation['duplicate_detection']},indent=2))

if __name__=='__main__':
    main()
