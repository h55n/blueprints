import json,runpy
from types import SimpleNamespace
import pytest
import dns.resolver,dns.exception
from kestra import Kestra


def probe(monkeypatch, results, previous=None, dry=False, threshold=2, hostname='app.example.com'):
    monkeypatch.setenv('HOSTNAME_TO_CHECK',hostname)
    monkeypatch.setenv('DNS_SERVER','1.1.1.1')
    monkeypatch.setenv('PREVIOUS_STATE',json.dumps(previous or {}))
    monkeypatch.setenv('DRY_RUN',str(dry).lower())
    monkeypatch.setenv('MIN_OBSERVATIONS',str(threshold))
    class Resolver:
        def resolve(self,name,kind,search=False):
            expected_name,expected_kind,result=results.pop(0)
            assert (name,kind)==(expected_name,expected_kind)
            if isinstance(result,Exception):raise result
            return result
    monkeypatch.setattr(dns.resolver,'Resolver',Resolver)
    captured=[]
    monkeypatch.setattr(Kestra,'outputs',lambda x: captured.append(x))
    runpy.run_path('/tmp/cname_probe.py')
    assert not results
    return captured[0]


def cname():return [SimpleNamespace(target='retired.example.net.')]
def missing():return [('app.example.com','CNAME',cname()),('retired.example.net','A',dns.resolver.NXDOMAIN())]

def test_first_missing(monkeypatch):
    x=probe(monkeypatch,missing());assert x['consecutive']==1 and not x['eligible']
def test_second_missing_ticket(monkeypatch):
    x=probe(monkeypatch,missing(),{'status':'NXDOMAIN','target':'retired.example.net','consecutive':1})
    assert x['eligible'] and x['state']['reported_target']=='retired.example.net'
def test_third_suppressed(monkeypatch):
    x=probe(monkeypatch,missing(),{'status':'NXDOMAIN','target':'retired.example.net','consecutive':2,'reported_target':'retired.example.net'})
    assert not x['eligible']
def test_changed_target_resets(monkeypatch):
    x=probe(monkeypatch,missing(),{'status':'NXDOMAIN','target':'other.example.net','consecutive':40})
    assert x['consecutive']==1 and not x['eligible']
def test_no_a_is_not_missing(monkeypatch):
    x=probe(monkeypatch,[('app.example.com','CNAME',cname()),('retired.example.net','A',dns.resolver.NoAnswer())])
    assert x['status']=='EXISTS' and not x['eligible']
@pytest.mark.parametrize('error',[dns.resolver.NXDOMAIN(),dns.resolver.NoAnswer()])
def test_no_source_record(monkeypatch,error):
    x=probe(monkeypatch,[('app.example.com','CNAME',error)])
    assert x['status']=='NO_CNAME' and x['consecutive']==0
@pytest.mark.parametrize('error',[dns.exception.Timeout(),dns.resolver.NoNameservers()])
@pytest.mark.parametrize('stage',['CNAME','A'])
def test_dns_errors_fail(monkeypatch,error,stage):
    seq=[('app.example.com','CNAME',cname()),('retired.example.net','A',error)] if stage=='A' else [('app.example.com','CNAME',error)]
    with pytest.raises(type(error)):probe(monkeypatch,seq)
def test_dry_does_not_mark_reported(monkeypatch):
    x=probe(monkeypatch,missing(),{'status':'NXDOMAIN','target':'retired.example.net','consecutive':1},dry=True)
    assert x['eligible'] and x['state']['reported_target']==''
@pytest.mark.parametrize('name',['http://example.com','x..example.com','-bad.example.com','example','x;echo.example.com'])
def test_bad_names(monkeypatch,name):
    with pytest.raises(ValueError):probe(monkeypatch,[],hostname=name)
def test_bad_threshold(monkeypatch):
    with pytest.raises(ValueError):probe(monkeypatch,missing(),threshold=1)
