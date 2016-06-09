#!/usr/bin/env python

import yaml
import logging
import os
import os.path
import sys
import subprocess


class AnsibleConfigProvider(object):
    parameters_file_path = os.path.abspath('parameters.yaml')
    ssh_key_file_path = os.path.expanduser('~/.ssh/id_rsa')
    ssh_config_file_path = os.path.expanduser('~/.ssh/config')
    ansible_inventory_file_path = os.path.abspath('inventory/slingshot')
    ansible_vars_all_file_path = os.path.abspath('group_vars/all.yaml')
    my_parameters = None
    my_log = None

    def __initialize__(self):
        self.my_parameters = None
        self.my_log = None

    @property
    def parameters(self):
        if self.my_parameters is None:
            with open(self.parameters_file_path, 'r') as stream:
                self.my_parameters = yaml.load(stream)
            self.log.info(
                "read parameters from '%s'" % self.parameters_file_path
            )
        return self.my_parameters

    @property
    def log(self):
        if self.my_log is None:
            l = logging.getLogger(__name__)
            l.setLevel(logging.DEBUG)
            ch = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            ch.setFormatter(formatter)
            l.addHandler(ch)
            self.my_log = l
        return self.my_log

    def prepare(self):
        self.configure_ssh()
        self.configure_ansible()

    def write_to_file(self, path, content):
        dir_path = os.path.dirname(path)
        if not os.path.isdir(dir_path):
            os.makedirs(dir_path)

        with open(path, 'w') as stream:
            stream.write(content)

    def configure_ssh(self):
        self.configure_ssh_key()
        self.configure_ssh_config()

    def configure_ssh_config(self):
        output = []
        for host in self.parameters['inventory']:
            if 'bastion' in host['roles']:
                output += [
                    'Host bastion',
                    '   Hostname %s' % host['publicIP'],
                    '   User core',
                    '   ForwardAgent yes',
                    '   ControlMaster auto',
                    '   ControlPath ~/.ssh/ansible-%r@%h:%p',
                    '   ControlPersist 5m',
                    '   StrictHostKeyChecking no',
                    ''
                ]
            elif host['publicIP'] is None:
                output += [
                    'Host %s' % host['privateIP'],
                    '   StrictHostKeyChecking no',
                    '   ProxyCommand ssh -q bastion ncat %h 22',
                    ''
                ]
        self.write_to_file(
            self.ssh_config_file_path,
            '\n'.join(output),
        )
        self.log.info(
            "successfully wrote ssh config to '%s'" % self.ssh_config_file_path
        )

    def configure_ssh_key(self):
        try:
            ssh = self.parameters['general']['authentication']['ssh']
            key = ssh['privateKey']

            if os.path.exists(self.ssh_key_file_path):
                self.log.warn(
                    "Won't overwrite the key in '%s'" % self.ssh_key_file_path
                )
                return None

            self.write_to_file(self.ssh_key_file_path, key)

            os.chmod(self.ssh_key_file_path, 0600)

            self.log.info(
                "successfully wrote ssh key to '%s'" % self.ssh_key_file_path
            )
        except Exception as e:
            self.log.warn('writing of ssh key failed: %s' % e)

    def configure_ansible(self):
        self.configure_ansible_inventory()
        self.configure_ansible_params()

    def configure_ansible_params(self):
        inputConf = self.parameters['general']['cluster']['kubernetes']
        outputConf = {
            'source_type': 'packageManager',
            'cluster_name':
            inputConf['dns']['domainName'],
            'kube_master_api_port':
            inputConf['masterApiPort'],
            'kube_service_addresses':
            inputConf['serviceNetwork'],
            'networking':
            inputConf['networking'],
            'flannel_subnet':
            inputConf['flannel']['subnet'],
            'flannel_prefix':
            inputConf['flannel']['prefix'],
            'flannel_host_prefix':
            inputConf['flannel']['hostPrefix'],
            'cluster_logging':
            inputConf['addons']['clusterLogging'],
            'cluster_monitoring':
            inputConf['addons']['clusterMonitoring'],
            'kube-ui':
            inputConf['addons']['kubeUI'],
            'kube-dash':
            inputConf['addons']['kubeDash'],
        }

        if inputConf['dns']['replicas'] > 0:
            outputConf['dns_setup'] = True
            outputConf['dns_replicas'] = \
                inputConf['dns']['replicas']
        else:
            outputConf['dns_setup'] = False

        if 'interface' in inputConf:
            interface = inputConf['interface']
            outputConf['flannel_opts'] = '--iface="%s"' % interface
            outputConf['apiserver_extra_args'] = \
                '--advertise-address={{ ansible_%s.ipv4.address }}' % interface

        path = self.ansible_vars_all_file_path
        contents = [yaml.dump(outputConf, default_flow_style=False)]
        if 'custom' in self.parameters:
            customConf = self.parameters['custom']
            if 'ansible_vars_pre' in customConf:
                contents.insert(0, customConf['ansible_vars_pre'])
            if 'ansible_vars_post' in customConf:
                contents.append(customConf['ansible_vars_post'])

        content = '\n'.join(contents)
        self.write_to_file(path, content)
        self.log.info(
            "successfully wrote group_vars key to '%s'" % path
        )
        self.log.info("content:\n%s", content)

    def configure_ansible_inventory(self):
        self.write_to_file(
            self.ansible_inventory_file_path,
            self.ansible_inventory()
        )
        self.log.info(
            "successfully wrote ansible inventory to '%s'" %
            self.ansible_inventory_file_path
        )
        pass

    def ansible_inventory(self):
        content = """[masters]
%s
[nodes]
%s
[etcd:children]
masters

[kubernetes:children]
nodes
masters

[coreos:children]
kubernetes
""" % (
            self.ansible_hosts('master'),
            self.ansible_hosts('worker'),
        )
        return content

    def ansible_hosts(self, role):
        output = ''
        for host in self.parameters['inventory']:
            if role in host['roles']:
                for ip in ['publicIP', 'privateIP']:
                    if host[ip] is not None:
                        output += "%s \n" % host[ip]
                        break

        return output

    def run_command(self, cmd):
        p = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        p.communicate()

    def apply(self):
        self.prepare()
        self.run_command(
            ["ansible-playbook", "cluster.yaml", "-l", "coreos"],
        )

    def discover(self):
        print("""provider:
  type: config
  version: 1
commands:
  apply:
    execs:
      -
        - apply
    type: docker
    parameterFile: %s
    persistPaths: []""" % os.path.basename(self.parameters_file_path))

    def command(self, argv):
        cmd = argv[1]
        if cmd == 'discover':
            return self.discover()
        elif cmd == 'apply':
            return self.apply()
        else:
            print("Unknown command '%s'" % cmd)
            sys.exit(1)


def main():
    acp = AnsibleConfigProvider()
    acp.command(sys.argv)


if __name__ == "__main__":
    main()