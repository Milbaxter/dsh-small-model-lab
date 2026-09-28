"""Export the credential-free pinned runner image for installation in Harbor tasks."""
import argparse
from pathlib import Path
import subprocess
import tarfile
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='dsh-small-model-lab-openrouter-runner:latest')
    parser.add_argument('--output',type=Path,default=Path('.local/harbor-runtime.tar.gz'))
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        cid=subprocess.check_output(['docker','create',args.image],text=True).strip()
        try:
            subprocess.run(['docker','cp',cid+':/usr/local',str(root/'runtime')],check=True)
            subprocess.run(['docker','cp',cid+':/opt/lab',str(root/'lab')],check=True)
        finally:subprocess.run(['docker','rm',cid],check=True,capture_output=True)
        for folder in (root/'lab/.local',root/'lab/.env',root/'lab/private-tasks'):
            if folder.exists():raise ValueError('Private data unexpectedly present in runner image')
        with tarfile.open(args.output,'w:gz') as archive:
            archive.add(root/'runtime',arcname='runtime');archive.add(root/'lab',arcname='lab')
    print(args.output)


if __name__=='__main__':main()
