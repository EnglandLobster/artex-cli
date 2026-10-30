#!/usr/bin/env python3
"""Install the standalone client and its agent skill locally or over SSH.

Does not build, replace, configure, or restart the ARTEX backend.
"""
import argparse
import io
import json
import pathlib
import shlex
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The installer receives a bounded archive over stdin, never shell-interpolated
# file content. Only CLI-owned destinations are updated; unrelated files stay.
INSTALL = r'''
import io,json,os,pathlib,shutil,sys,tarfile,tempfile
cfg=json.loads(sys.argv[1])
prefix=pathlib.Path(cfg["prefix"]).expanduser().resolve()
link=pathlib.Path(cfg["bin_dir"]).expanduser()/"artexctl"
skill=pathlib.Path(cfg["skill_dir"]).expanduser()/"artex"
marker=prefix/".artex-cli-install"
if prefix.exists() and any(prefix.iterdir()) and not marker.exists():
    raise SystemExit("Refusing to overwrite unmanaged prefix: "+str(prefix))
if skill.exists() and not (skill/".artex-cli-skill").exists():
    raise SystemExit("Refusing to overwrite unmanaged skill: "+str(skill))
if link.exists() or link.is_symlink():
    if not link.is_symlink() or link.resolve() != prefix/"artexctl":
        raise SystemExit("Refusing to replace unrelated command: "+str(link))
with tempfile.TemporaryDirectory() as tmp:
    stage=pathlib.Path(tmp)
    with tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz") as archive:
        for member in archive:
            path=pathlib.PurePosixPath(member.name)
            if member.issym() or member.islnk() or path.is_absolute() or ".." in path.parts:
                raise SystemExit("Unsafe package member")
            if not member.isfile(): continue
            target=stage/member.name
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(member) as source,target.open("wb") as dest:
                shutil.copyfileobj(source,dest)
    prefix.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(stage/"artexctl",prefix/"artexctl.new")
    (prefix/"artexctl.new").chmod(0o755)
    os.replace(prefix/"artexctl.new",prefix/"artexctl")
    marker.touch()
    skill.mkdir(parents=True,exist_ok=True)
    for source in (stage/"skill").rglob("*"):
        if source.is_file():
            target=skill/source.relative_to(stage/"skill")
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
    (skill/".artex-cli-skill").touch()
    link.parent.mkdir(parents=True,exist_ok=True)
    if not link.is_symlink(): link.symlink_to(prefix/"artexctl")
print(json.dumps({"executable":str(link),"skill":str(skill),"prefix":str(prefix)}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh", help="SSH alias; omitted means local installation")
    parser.add_argument("--prefix", help="CLI-owned install directory")
    parser.add_argument("--bin-dir", help="Directory for the artexctl symlink")
    parser.add_argument("--skill-dir", default="~/.agents/skills", help="Agent skill parent directory (default: ~/.agents/skills)")
    args = parser.parse_args()
    if args.ssh and (args.ssh.startswith("-") or any(c.isspace() for c in args.ssh)):
        parser.error("--ssh must be one host alias or user@host")
    prefix = args.prefix or ("/opt/artex-cli" if args.ssh else "~/.local/share/artex-cli")
    bin_dir = args.bin_dir or ("/usr/local/bin" if args.ssh else "~/.local/bin")
    # Catalog freshness is only checkable next to the backend source tree; a
    # standalone checkout ships a prebuilt catalog.json instead.
    if (ROOT / "server").is_dir():
        subprocess.run([sys.executable, str(ROOT / "cli/generate_catalog.py"), "--check"], check=True)
    subprocess.run([sys.executable, str(ROOT / "cli/build.py")], check=True)
    package = io.BytesIO()
    with tarfile.open(fileobj=package, mode="w:gz") as archive:
        archive.add(ROOT / "dist/artexctl", arcname="artexctl")
        for file in sorted((ROOT / "cli/skill/artex").rglob("*")):
            if file.is_file():
                archive.add(file, arcname="skill/" + str(file.relative_to(ROOT / "cli/skill/artex")))
    cfg = json.dumps(dict(prefix=prefix, bin_dir=bin_dir, skill_dir=args.skill_dir))
    if args.ssh:
        command = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", args.ssh,
                   "python3 -c " + shlex.quote(INSTALL) + " " + shlex.quote(cfg)]
    else:
        command = [sys.executable, "-c", INSTALL, cfg]
    subprocess.run(command, input=package.getvalue(), check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode)
