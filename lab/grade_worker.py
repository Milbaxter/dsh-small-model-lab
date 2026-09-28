"""Untrusted code execution in a second networkless container, without expected answers."""
import copy
import importlib.util
import json
from pathlib import Path
import sys


def main():
    request=json.load(sys.stdin)
    workspace=Path('/workspace')
    if request['kind']=='code':
        spec=importlib.util.spec_from_file_location('submission',workspace/'solution.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        results=[]
        for case in request['inputs']:
            arg=copy.deepcopy(case)
            results.append({'value':module.solve(arg),'unchanged':arg==case})
        print(json.dumps({'results':results}))
    else:
        results={}
        for name in request['files']:
            p=workspace/name
            if p.stat().st_size>1048576:raise ValueError('Oversized submission')
            results[name]=json.loads(p.read_text())
        print(json.dumps({'files':results}))


if __name__=='__main__':main()
