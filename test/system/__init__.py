# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os, sys, time, signal, httplib

__all__ = ['root', 'thrift_client']

from thrift.transport import TTransport
from thrift.transport import TSocket
from thrift.transport import THttpClient
from thrift.protocol import TBinaryProtocol
try:
    import avro.ipc as ipc
    import avro.protocol as protocol
except ImportError:
    pass

# add cassandra directory to sys.path
L = os.path.abspath(__file__).split(os.path.sep)[:-3]
root = os.path.sep.join(L)
_ipath = os.path.join(root, 'interface', 'thrift', 'gen-py')
sys.path.append(os.path.join(_ipath, 'cassandra'))
import Cassandra

def get_thrift_client(host='127.0.0.1', port=9170):
    socket = TSocket.TSocket(host, port)
    transport = TTransport.TBufferedTransport(socket)
    protocol = TBinaryProtocol.TBinaryProtocolAccelerated(transport)
    client = Cassandra.Client(protocol)
    client.transport = transport
    return client
thrift_client = get_thrift_client()

def get_avro_client(host='127.0.0.1', port=9170):
    schema = os.path.join(root, 'interface', 'cassandra.avpr')
    proto = protocol.parse(open(schema).read())
    client = ipc.HTTPTransceiver(host, port)
    return ipc.Requestor(proto, client)

pid_fname = "system_test.pid"
def pid():
    return int(open(pid_fname).read())

class BaseTester(object):
    # leave this True unless you are manually starting a server and then
    # running only a single test against it; tests assume they start
    # against an empty db.
    runserver = True
    client = None
    extra_args = []

    def open_client(self):
        raise NotImplementedError()

    def close_client(self):
        raise NotImplementedError()
    
    def define_schema(self):
        raise NotImplementedError()

    def setUp(self):
        if self.runserver:
            if os.path.exists(pid_fname):
                pid_path = os.path.join(root, pid_fname)
                print "Unclean shutdown detected, (%s found)" % pid_path
                sys.exit()

            # clean out old stuff
            import shutil
            # todo get directories from conf/storage-conf.xml
            for dirname in ['system', 'data', 'commitlog']:
                try:
                    shutil.rmtree('build/test/cassandra/' + dirname)
                except OSError:
                    pass
            # start the server
            import subprocess as sp
            os.chdir(root)
            os.environ['CASSANDRA_INCLUDE'] = 'test/cassandra.in.sh'
            args = ['bin/cassandra', '-p', pid_fname] + self.extra_args
            process = sp.Popen(args, stderr=sp.PIPE, stdout=sp.PIPE)
            time.sleep(0.1)

            # connect to it, with a timeout in case something went wrong
            start = time.time()
            while time.time() < start + 10:
                try:
                    self.open_client()
                except:
                    time.sleep(0.1)
                else:
                    break
            else:
                print "Couldn't connect to server; aborting regression test"
                # see if process is still alive
                process.poll()
                
                if process.returncode is None:
                    os.kill(pid(), signal.SIGKILL) # just in case
                else:
                    stdout_value, stderr_value = process.communicate()
                    print "Stdout: %s" % (stdout_value)
                    print "Stderr: %s" % (stderr_value)
                sys.exit()
        else:
            try:
                self.open_client()
            except:
                pass
        
        self.define_schema()

    def tearDown(self):
        if self.runserver:
            self.close_client()
            open('/tmp/kill', 'w').write('killing %s\n' % pid())
            os.kill(pid(), signal.SIGTERM)
            # TODO kill server with SIGKILL if it's still alive
            time.sleep(0.5)
            # TODO assert server is Truly Dead

class ThriftTester(BaseTester):
    client = thrift_client

    def open_client(self):
        self.client.transport.open()

    def close_client(self):
        self.client.transport.close()
        
    def define_schema(self):
        keyspace1 = Cassandra.KsDef('Keyspace1', 'org.apache.cassandra.locator.RackUnawareStrategy', 1, 'org.apache.cassandra.locator.EndPointSnitch', 
        [
            Cassandra.CfDef('Keyspace1', 'Standard1'),
            Cassandra.CfDef('Keyspace1', 'Standard2'), 
            Cassandra.CfDef('Keyspace1', 'StandardLong1', comparator_type='LongType'), 
            Cassandra.CfDef('Keyspace1', 'StandardLong2', comparator_type='LongType'), 
            Cassandra.CfDef('Keyspace1', 'Super1', column_type='Super', subcomparator_type='LongType', row_cache_size=1000, key_cache_size=0), 
            Cassandra.CfDef('Keyspace1', 'Super2', column_type='Super', subcomparator_type='LongType'), 
            Cassandra.CfDef('Keyspace1', 'Super3', column_type='Super', subcomparator_type='LongType'), 
            Cassandra.CfDef('Keyspace1', 'Super4', column_type='Super', subcomparator_type='UTF8Type')
        ])

        keyspace2 = Cassandra.KsDef('Keyspace2', 'org.apache.cassandra.locator.RackUnawareStrategy', 1, 'org.apache.cassandra.locator.EndPointSnitch',
        [
            Cassandra.CfDef('Keyspace2', 'Standard1'),
            Cassandra.CfDef('Keyspace2', 'Standard3'),
            Cassandra.CfDef('Keyspace2', 'Super3', column_type='Super', subcomparator_type='BytesType'),
            Cassandra.CfDef('Keyspace2', 'Super4', column_type='Super', subcomparator_type='TimeUUIDType'),
        ])

        keyspace3 = Cassandra.KsDef('Keyspace3', 'org.apache.cassandra.locator.RackUnawareStrategy', 5, 'org.apache.cassandra.locator.EndPointSnitch',
        [
            Cassandra.CfDef('Keyspace3', 'Standard1'),
        ])

        keyspace4 = Cassandra.KsDef('Keyspace4', 'org.apache.cassandra.locator.RackUnawareStrategy', 3, 'org.apache.cassandra.locator.EndPointSnitch',
        [
            Cassandra.CfDef('Keyspace4', 'Standard1'),
            Cassandra.CfDef('Keyspace4', 'Standard3'),
            Cassandra.CfDef('Keyspace4', 'Super3', column_type='Super', subcomparator_type='BytesType'),
            Cassandra.CfDef('Keyspace4', 'Super4', column_type='Super', subcomparator_type='TimeUUIDType')
        ])
        self.client.system_add_keyspace(keyspace1)
        self.client.system_add_keyspace(keyspace2)
        self.client.system_add_keyspace(keyspace3)
        self.client.system_add_keyspace(keyspace4)

class AvroTester(BaseTester):
    client = None
    extra_args = ['-a']

    def open_client(self):
        self.client = get_avro_client()

    def close_client(self):
        self.client.transceiver.conn.close()
    
    def define_schema(self):
        pass

# vim:ai sw=4 ts=4 tw=0 et
