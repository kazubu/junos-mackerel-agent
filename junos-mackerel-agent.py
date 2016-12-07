# -*- coding: utf-8 -*-

import argparse
import io
import os
import time
import urllib
import urllib2
import json
import re
import importlib

class Mackerel(object):
  def __init__(self, **kwargs):
    self.origin = kwargs.get('mackerel_origin', 'https://mackerel.io')
    api_key = kwargs.get('mackerel_api_key', None)
    if api_key is None:
      raise MackerelClientError(self.ERROR_MESSAGE_FOR_API_KEY_ABSENCE)

    self.api_key = api_key

  def get_host(self, host_id):
    uri = '/api/v0/hosts/{0}'.format(host_id)
    data = self._request(uri)

    return Host(**data['host'])

  def register_host(self, name, meta):
    uri = '/api/v0/hosts'
    headers = {'Content-Type': 'application/json'}
    params = json.dumps({'name': name, 'meta': meta})
    data = self._request(uri, method='POST', headers=headers, params=params)

    return data

  def update_host_status(self, host_id, status):
    if status not in ['standby', 'working', 'maintenance', 'poweroff']:
      raise MackerelClientError('no such status: {0}'.format(status))

    uri = '/api/v0/hosts/{0}/status'.format(host_id)
    headers = {'Content-Type': 'application/json'}
    params = json.dumps({'status': status})
    data = self._request(uri, method='POST', headers=headers, params=params)

    return data

  def retire_host(self, host_id):
    uri = '/api/v0/hosts/{0}/retire'.format(host_id)
    headers = {'Content-Type': 'application/json'}
    data = self._request(uri, method='POST', headers=headers, params="{}")

    return data

  def post_metrics(self, metrics):
    uri = '/api/v0/tsdb'
    headers = {'Content-Type': 'application/json'}
    params = json.dumps(metrics)
    data = self._request(uri, method='POST', headers=headers, params=params)

    return data

  def get_latest_metrics(self, host_ids, names):
    hosts_query = '&'.join(['hostId={0}'.format(id) for id in host_ids])
    names_query = '&'.join(['name={0}'.format(name) for name in names])
    uri = '/api/v0/tsdb/latest?{0}&{1}'.format(hosts_query, names_query)

    data = self._request(uri)

    return data

  def post_service_metrics(self, service_name, metrics):
    uri = '/api/v0/services/{0}/tsdb'.format(service_name)
    headers = {'Content-Type': 'application/json'}
    params = json.dumps(metrics)
    data = self._request(uri, method='POST', headers=headers, params=params)

    return data

  def get_hosts(self, **kwargs):
    uri = '/api/v0/hosts.json'
    params = {}

    if kwargs.get('service', None):
      params['service'] = kwargs.get('service')

    if kwargs.get('roles', None):
      params['roles'] = kwargs.get('roles')

    if kwargs.get('name', None):
      params['name'] = kwargs.get('name')

    hosts = self._request(uri, params=params)

    return [Host(**host) for host in hosts['hosts']]

  def _request(self, uri, method='GET', headers=None, params=None):
    uri = '{0}{1}'.format(self.origin, uri)
    if headers is None:
      headers = {'X-Api-Key': self.api_key}
    else:
      headers.update({'X-Api-Key': self.api_key})

    if method == 'GET':
      req = urllib2.Request(uri, None, headers)
      res = urllib2.urlopen(req)
    elif method == 'POST':
      req = urllib2.Request(uri, params, headers)
      res = urllib2.urlopen(req)
    else:
      message = '{0} is not supported.'.format(method)
      raise NotImplementedError(message)

    if res.getcode() != 200:
      message = '{0} {1} failed: {2}'.format(method, uri, res.getcode())
      raise MackerelClientError(message)

    data = json.loads(res.read())

    return data

class Host(object):
    MACKEREL_INTERFACE_NAME_PATTERN = re.compile(r'^(fxp0|em0|me0|vme).*')

    def __init__(self, **kwargs):
        self.args = kwargs
        self.name = kwargs.get('name', None)
        self.meta = kwargs.get('meta', None)
        self.type = kwargs.get('type', None)
        self.status = kwargs.get('status', None)
        self.memo = kwargs.get('memo', None)
        self.is_retired = kwargs.get('isRetired', None)
        self.id = kwargs.get('id', None)
        self.created_at = kwargs.get('createdAt', None)
        self.roles = kwargs.get('roles', None)
        self.interfaces = kwargs.get('interfaces', None)

    def ip_addr(self):
        for i in self.interfaces:
            if self.MACKEREL_INTERFACE_NAME_PATTERN.search(i['name']):
                return i['ipAddress']

    def mac_addr(self):
        for i in self.interfaces:
            if self.MACKEREL_INTERFACE_NAME_PATTERN.search(i['name']):
                return i['macAddress']

    def __repr__(self):
        repr = '<Host('
        repr += 'name={0}, meta={1}, type={2}, status={3}, memo={4},'
        repr += 'is_retired={5}, id={6}, created_at={7}, roles={8},'
        repr += 'interfaces={9})'
        return repr.format(self.name, self.meta, self.type, self.status,
                           self.memo, self.is_retired, self.id, self.created_at, self.roles, self.interfaces)

class JunosMetrics(object):
  def __init__(self, **kwargs):
    self.junos = importlib.import_module('jnpr.junos')
    self.ethport = importlib.import_module('jnpr.junos.op.ethport')
    self.dev = self.junos.Device()
    self.dev.open()
    self.last_metric = LastMetricStorage('/var/tmp/lastmetrics.json')

  def loadavg5(self):
    return

  def cpu(self):
    return

  def memory(self):
    return

  def disk(self):
    return

  def interface(self):
    ports = self.ethport.EthPortTable(self.dev)
    ports.get()
    result = []
    for k,v in ports.items():
      ifname = k.replace('/','-').replace('.','-')
      for k2,v2 in v:
        if k2 == 'rx_bytes':
          rxbytes = v2
        elif k2 == 'tx_bytes':
          txbytes = v2

      drx = (self.last_metric.delta("interface.%s.rxBytes" %(ifname), int(rxbytes)))
      dtx = (self.last_metric.delta("interface.%s.txBytes" %(ifname), int(txbytes)))

      result.append({'name': "interface.%s.rxBytes.delta" %(ifname), 'value': drx})
      result.append({'name': "interface.%s.txBytes.delta" %(ifname), 'value': dtx})

    return result

  def filesystem(self):
    return

class LastMetricStorage(object):
  def __init__(self, db_path, **kwargs):
    self.db_path = db_path
    if os.path.isfile(db_path):
      self.load()
    else:
      self.data = {}

  def set(self, key, value):
    self.data[key] = value
    self.save()

  def read(self, key):
    if self.data.has_key(key):
      return self.data[key]
    else:
      return 0

  def delta(self, key, current):
    last = self.read(key)
    self.set(key, current)

    if last > current or last == 0:
      return current
    else:
      return current - last

  def save(self):
    with io.open(self.db_path, 'w') as f:
      f.write(unicode(json.dumps(self.data, ensure_ascii=False)))
    self.load()

  def load(self):
    self.data = json.loads(open(self.db_path).read())

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("-apikey", action='store', nargs=None, const=None, default=None, type=str, choices=None, help='specify Mackerel API Key', metavar=None)
  parser.add_argument('-mode', action='store', nargs=None, const=None, default='cron', type=str, choices=None, help='specify mode (init, cron).', metavar=None)
  parser.add_argument('-hostid', action='store', nargs=None, const=None, default=None, type=str, choices=None, help='specify hostid.', metavar=None)
  args = parser.parse_args()

  if args.apikey is None:
    raise Error("API key is mandatory")

  mackerel = Mackerel(mackerel_api_key=args.apikey)

  if args.mode == 'init':
    if args.hostid != None:
      raise Error('Host ID is not needed for init')

    init(mackerel)
  elif args.mode == 'retire':
    if args.hostid == None:
      raise Error('Host ID is mandatory for retire')

    retire(mackerel, args.hostid)
  elif args.mode == 'cron':
    if args.hostid == None:
      raise Error('Host ID is mandatory for cron')

    cron(mackerel, args.hostid)
  else:
    raise Error("unknown mode: "+mode)


def init(mackerel):
  result = mackerel.register_host(os.uname()[1], "")
  print "Register succeed! Host ID :" + result['id']

def retire(mackerel, hostid):
  result = mackerel.retire_host(hostid)
  print "Retire succeed!"

def cron(mackerel, hostid):
  data = []
  current_time = int(time.time())
  metricdb = JunosMetrics()
  interface = metricdb.interface()
  map(lambda x:x.update({'hostId':hostid, 'time': current_time}), interface)
  data.extend(interface)

  mackerel.post_metrics(data)
  print "Post succeed!"
  print "data:"
  print data

if __name__ == "__main__":
  main()
