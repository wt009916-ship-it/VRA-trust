"""Ownership recovery uses real file identities/locks and disposable directories."""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time

import pytest

from backend import native_ownership as own
from tests.lifetime_probe import ProcessHandle


def test_active_lease_survives_recovery_and_normal_close_removes_data(tmp_path):
    with own.owned_temporary(tmp_path) as data:
        (data/'source').write_bytes(b'synthetic original')
        result=own.recover(tmp_path)
        assert result=={'recovered':[],'active':1}
        assert (data/'source').read_bytes()==b'synthetic original'
    assert not data.exists()
    assert own.recover(tmp_path)=={'recovered':[],'active':0}


def orphan(parent,contents='synthetic'):
    code='from pathlib import Path; import os; from backend.native_ownership import owned_temporary; '
    code+='cm=owned_temporary('+repr(str(parent))+'); p=cm.__enter__(); (p/"file").write_text('+repr(contents)+'); print(str(p),flush=True); os._exit(0)'
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    return Path(result.stdout.strip())


def test_dead_owner_is_recovered_without_touching_neighbor(tmp_path):
    outside=tmp_path/'original';outside.write_text('retain')
    data=orphan(tmp_path)
    assert (data/'file').read_text()=='synthetic'
    result=own.recover(tmp_path)
    assert result=={'recovered':[data.parent.name],'active':0}
    assert not data.exists() and outside.read_text()=='retain'


@pytest.mark.parametrize('field,value',[('id','0'*32),('data_identity',{'device':0,'inode':1}),('state','made-up')])
def test_corrupt_journal_preserves_data(tmp_path,field,value):
    data=orphan(tmp_path);record=data.parent/'record.json';original=record.read_bytes()
    changed=json.loads(original);changed[field]=value;record.write_text(json.dumps(changed))
    with pytest.raises(own.RecoveryError):own.recover(tmp_path)
    assert (data/'file').read_text()=='synthetic'
    record.write_bytes(original)
    assert own.recover(tmp_path)['recovered']==[data.parent.name]


def test_missing_journal_with_data_refuses_cleanup(tmp_path):
    data=orphan(tmp_path);record=data.parent/'record.json';saved=record.read_bytes();record.unlink()
    with pytest.raises(own.RecoveryError,match='Missing native journal'):own.recover(tmp_path)
    assert (data/'file').exists()
    from backend.private_storage import private_open
    with private_open(record) as stream:stream.write(saved)
    assert own.recover(tmp_path)['recovered']==[data.parent.name]


@pytest.mark.skipif(sys.platform!='linux',reason='Linux symlink attack; Windows junction covered separately')
def test_linked_data_is_retained_and_external_source_survives(tmp_path):
    data=orphan(tmp_path);outside=tmp_path/'outside';outside.mkdir();(outside/'original').write_text('retain')
    os.symlink(outside,data/'link',target_is_directory=True)
    with pytest.raises((own.RecoveryError,ValueError)):own.recover(tmp_path)
    assert (outside/'original').read_text()=='retain'
    (data/'link').unlink()
    assert own.recover(tmp_path)['recovered']==[data.parent.name]


def run_owned_child(code, *args):
    # Base executable avoids the Windows venv redirector; tests need stdlib only.
    python=getattr(sys,'_base_executable',sys.executable)
    result=subprocess.run([python,'-c',textwrap.dedent(code),*map(str,args)],
                          capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    return result


def test_inherited_lease_blocks_recovery_after_owner_exit(tmp_path):
    ready=tmp_path/'ready.json';release=tmp_path/'release';handle=None
    child_code=textwrap.dedent('''
        import json,os,sys,time
        from pathlib import Path
        from backend.native_ownership import verify_inherited
        held=verify_inherited(json.loads(sys.argv[1]))
        Path(sys.argv[2]).write_text(json.dumps({'pid':os.getpid(),'data':sys.argv[4]}))
        deadline=time.monotonic()+45
        while not Path(sys.argv[3]).exists() and time.monotonic()<deadline:time.sleep(.01)
    ''')
    caller_code='''
        import os,sys,json,subprocess,time
        from pathlib import Path
        from backend.native_ownership import owned_temporary,inherit_leases
        cm=owned_temporary(sys.argv[1]);data=cm.__enter__()
        (data/'original').write_text('retained while supervisor lives')
        with inherit_leases([data/'original']) as binding:
            subprocess.Popen([sys.executable,'-c',sys.argv[4],json.dumps(binding['items']),
                sys.argv[2],sys.argv[3],str(data)],stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**binding['popen'])
        deadline=time.monotonic()+10
        while not Path(sys.argv[2]).exists() and time.monotonic()<deadline:time.sleep(.01)
        assert Path(sys.argv[2]).exists(),'inherited child readiness timeout'
        os._exit(0)
    '''
    try:
        run_owned_child(caller_code,tmp_path,ready,release,child_code)
        record=json.loads(ready.read_text());data=Path(record['data']);handle=ProcessHandle(record['pid'])
        assert not handle.exited()
        assert own.recover(tmp_path)=={'recovered':[],'active':1}
        assert (data/'original').read_text()=='retained while supervisor lives'
        release.touch();deadline=time.monotonic()+5
        while not handle.exited() and time.monotonic()<deadline:time.sleep(.01)
        assert handle.exited()
        assert own.recover(tmp_path)=={'recovered':[data.parent.name],'active':0}
    finally:
        release.touch()
        if handle is not None:
            try:handle.stop()
            finally:handle.close()


@pytest.mark.parametrize('stage',['entry_created','lease_created','initial_record','data_created','committed'])
def test_allocation_crash_is_recoverable(tmp_path,stage):
    code='''
        import os,sys
        from backend import native_ownership as own
        stage=sys.argv[2];mkdir=own.private_mkdir;write=own._write;lease=own.Lease
        def make(path):
            result=mkdir(path)
            if (stage=='entry_created' and len(path.name)==32) or (stage=='data_created' and path.name=='data'):os._exit(0)
            return result
        def save(entry,value):
            write(entry,value)
            if stage=='initial_record' and value['data_identity'] is None:os._exit(0)
        class CrashLease(lease):
            def __init__(self,path,create=False):
                super().__init__(path,create)
                if stage=='lease_created' and path.name=='lease':os._exit(0)
        own.private_mkdir=make;own._write=save;own.Lease=CrashLease
        with own.owned_temporary(sys.argv[1]):
            assert stage=='committed';os._exit(0)
    '''
    run_owned_child(code,tmp_path,stage)
    entries=[p for p in own.registry(tmp_path).iterdir() if p.is_dir()]
    assert len(entries)==1
    assert own.recover(tmp_path)=={'recovered':[entries[0].name],'active':0}
    assert own.recover(tmp_path)=={'recovered':[],'active':0}


@pytest.mark.parametrize('stage',['cleaning_record','data_removed','journal_removed','lease_removed'])
def test_recovery_itself_can_be_interrupted_and_resumed(tmp_path,stage):
    data=orphan(tmp_path)
    code='''
        import os,sys
        from pathlib import Path
        from backend import native_ownership as own
        stage=sys.argv[2];write=own._write;remove=own.shutil.rmtree;unlink=Path.unlink
        def save(entry,value):
            write(entry,value)
            if stage=='cleaning_record' and value['state']=='cleaning':os._exit(0)
        def tree(path,*args,**kwargs):
            remove(path,*args,**kwargs)
            if stage=='data_removed':os._exit(0)
        def file(path,*args,**kwargs):
            unlink(path,*args,**kwargs)
            if (stage=='journal_removed' and path.name=='record.json') or (stage=='lease_removed' and path.name=='lease'):os._exit(0)
        own._write=save;own.shutil.rmtree=tree;Path.unlink=file
        own.recover(sys.argv[1]);raise AssertionError('crash point not exercised')
    '''
    run_owned_child(code,tmp_path,stage)
    assert own.recover(tmp_path)=={'recovered':[data.parent.name],'active':0}
    assert not data.parent.exists()


def test_replaced_data_directory_is_not_adopted(tmp_path):
    data=orphan(tmp_path);saved=data.with_name('saved')
    data.rename(saved)
    from backend.private_storage import private_mkdir
    private_mkdir(data);(data/'unrelated').write_text('retain')
    with pytest.raises(own.RecoveryError,match='identity changed'):own.recover(tmp_path)
    assert (data/'unrelated').read_text()=='retain' and (saved/'file').read_text()=='synthetic'
    (data/'unrelated').unlink();data.rmdir();saved.rename(data)
    assert own.recover(tmp_path)['recovered']==[data.parent.name]


@pytest.mark.parametrize('receipt',[None,{}, {'verified':False,'count':0},{'verified':True,'count':99}])
def test_missing_or_wrong_lease_receipt_rejects_native_success(tmp_path,monkeypatch,receipt):
    from backend import execution
    from tests.test_execution import run_probe
    read=execution._receipt
    monkeypatch.setattr(execution,'_receipt',lambda p,n:{**read(p,n),'workspace_leases':receipt})
    with pytest.raises(execution.ExecutionError,match='receipt'):
        run_probe(tmp_path,'print("actual native success, invalid ownership receipt")')


@pytest.mark.skipif(sys.platform!='win32',reason='Windows AppContainer lifecycle')
@pytest.mark.parametrize('stage',['reserved','created','confirmed'])
def test_appcontainer_profile_creation_crash_recovers_exact_profile(tmp_path,stage):
    code='''
        import os,sys,tempfile,json
        from backend import native_windows as native
        tempfile.tempdir=sys.argv[1]
        reserve=native.reserve_profile;confirm=native.confirm_profile
        def reserved(root):
            name=reserve(root)
            if sys.argv[2]=='reserved':print(json.dumps({'data':str(root),'name':name}),flush=True);os._exit(0)
            return name
        def created(root,sid,path):
            if sys.argv[2]=='created':print(json.dumps({'data':str(root),'name':path.name}),flush=True);os._exit(0)
            return confirm(root,sid,path)
        native.reserve_profile=reserved;native.confirm_profile=created
        with native.staging() as scope:
            print(json.dumps({'data':str(scope['root']),'name':scope['profile']}),flush=True);os._exit(0)
    '''
    result=run_owned_child(code,tmp_path,stage);record=json.loads(result.stdout);data=Path(record['data'])
    profile=Path(os.environ['LOCALAPPDATA'])/'Packages'/record['name']
    try:
        assert record['name'].casefold()==('VRA.Engine.Managed.'+data.parent.name).casefold()
        assert profile.exists()==(stage!='reserved')
        assert own.recover(tmp_path)=={'recovered':[data.parent.name],'active':0}
        assert not profile.exists() and not data.parent.exists()
    finally:
        # Exact freshly allocated profile only; failure cleanup is not evidence.
        if profile.exists():own._profile_api()[3].DeleteAppContainerProfile(record['name'])


@pytest.mark.skipif(sys.platform!='win32',reason='Windows junction rejection')
def test_junction_is_retained_without_touching_external_source(tmp_path):
    data=orphan(tmp_path);outside=tmp_path/'outside';outside.mkdir();(outside/'original').write_text('retain')
    junction=data/'junction'
    # Only create a link inside this exact fresh fixture. No shell delete/move.
    assert all(not any(c in str(p) for c in '&|<>^%!"\r\n') for p in (junction,outside))
    result=subprocess.run(['cmd','/c','mklink','/J',str(junction),str(outside)],capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr
    try:
        with pytest.raises((own.RecoveryError,ValueError)):own.recover(tmp_path)
        assert (outside/'original').read_text()=='retain' and (data/'file').read_text()=='synthetic'
    finally:os.rmdir(junction)  # removes the junction itself, never the target tree
    assert own.recover(tmp_path)['recovered']==[data.parent.name]
