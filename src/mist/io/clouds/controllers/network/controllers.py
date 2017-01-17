"""Definition of cloud-specific network subcontroller classes.

This file should only contain subclasses of `BaseNetworkController`.

"""

import logging

from mist.io.helpers import rename_kwargs
from mist.io.exceptions import NetworkNotFoundError, SubnetNotFoundError
from mist.io.clouds.controllers.network.base import BaseNetworkController


log = logging.getLogger(__name__)


class AmazonNetworkController(BaseNetworkController):

    def _create_network__parse_args(self, kwargs):
        rename_kwargs(kwargs, 'cidr', 'cidr_block')

    def _create_subnet__parse_args(self, subnet, kwargs):
        kwargs['vpc_id'] = subnet.network.network_id
        rename_kwargs(kwargs, 'cidr', 'cidr_block')

    def _list_networks__parse_libcloud_object(self, network, libcloud_network):
        network.cidr = libcloud_network.cidr_block
        network.default = libcloud_network.extra.pop('is_default') is 'true'
        network.instance_tenancy = libcloud_network.extra.pop(
                                           'instance_tenancy')

    def _list_subnets__parse_args(self, network, kwargs):
        kwargs['filters'] = {'vpc-id': network.network_id}

    def _list_subnets__parse_libcloud_object(self, subnet, libcloud_subnet):
        subnet.cidr = libcloud_subnet.extra.pop('cidr_block')
        subnet.availability_zone = libcloud_subnet.extra.pop('zone')

    def _delete_network__parse_args(self, network, kwargs):
        kwargs['vpc'] = self._get_libcloud_network(network)

    def _delete_subnet__parse_args(self, subnet, kwargs):
        kwargs['subnet'] = self._get_libcloud_subnet(subnet)

    def _get_libcloud_network(self, network):
        kwargs = {'network_ids': [network.network_id]}
        networks = self.ctl.compute.connection.ex_list_networks(**kwargs)
        if networks:
            return networks[0]
        raise NetworkNotFoundError('Network %s with network_id %s' %
                                   (network.title, network.network_id))

    def _get_libcloud_subnet(self, subnet):
        kwargs = {'subnet_ids': [subnet.subnet_id]}
        subnets = self.ctl.compute.connection.ex_list_subnets(**kwargs)
        if subnets:
            return subnets[0]
        raise SubnetNotFoundError('Subnet %s with subnet_id %s' %
                                  (subnet.title, subnet.subnet_id))


class GoogleNetworkController(BaseNetworkController):

    def _create_network__parse_args(self, kwargs):
        kwargs['cidr'] = kwargs['cidr'] if kwargs['mode'] == 'legacy' else None

    def _create_subnet__parse_args(self, subnet, kwargs):
        kwargs['network'] = subnet.network.title

    def _create_subnet__create_libcloud_subnet(self, kwargs):
        return self.ctl.compute.connection.ex_create_subnetwork(**kwargs)

    def _list_networks__parse_libcloud_object(self, network, libcloud_network):
        network.cidr = libcloud_network.cidr
        network.mode = libcloud_network.mode
        network.gateway_ip = libcloud_network.extra.pop('gatewayIPv4')

    def _list_subnets__parse_libcloud_object(self, subnet, libcloud_subnet):
        subnet.cidr = libcloud_subnet.cidr
        subnet.region = libcloud_subnet.region.name
        subnet.gateway_ip = libcloud_subnet.extra.pop('gatewayAddress')

    def _list_subnets__fetch_subnets(self, network, kwargs):
        subnets = self.ctl.compute.connection.ex_list_subnetworks(**kwargs)
        return [subnet for subnet in subnets if
                subnet.network.id == network.network_id]

    def _delete_network__parse_args(self, network, kwargs):
        kwargs['network'] = self._get_libcloud_network(network)

    def _delete_network__delete_libcloud_network(self, kwargs):
        self.ctl.compute.connection.ex_destroy_network(**kwargs)

    def _delete_subnet__parse_args(self, subnet, kwargs):
        kwargs['name'] = subnet.title
        kwargs['region'] = subnet.region

    def _delete_subnet__delete_libcloud_subnet(self, kwargs):
        self.ctl.compute.connection.ex_destroy_subnetwork(**kwargs)

    def _get_libcloud_network(self, network):
        return self.ctl.compute.connection.ex_get_network(network.title)

    def _get_libcloud_subnet(self, subnet):
        kwargs = {'name': subnet.title,
                  'region': subnet.region}
        return self.ctl.compute.connection.ex_get_subnetwork(**kwargs)


class OpenStackNetworkController(BaseNetworkController):

    def _create_subnet__parse_args(self, subnet, kwargs):
        kwargs['network_id'] = subnet.network.network_id

    def _list_networks__parse_libcloud_object(self, network, libcloud_network):
        network.shared = libcloud_network.extra.pop('shared')
        network.admin_state_up = libcloud_network.extra.pop('admin_state_up')
        network.router_external = libcloud_network.router_external

    def _list_subnets__parse_libcloud_object(self, subnet, libcloud_subnet):
        subnet.cidr = libcloud_subnet.cidr
        subnet.gateway_ip = libcloud_subnet.gateway_ip
        subnet.enable_dhcp = libcloud_subnet.enable_dhcp
        subnet.dns_nameservers = libcloud_subnet.dns_nameservers
        subnet.allocation_pools = libcloud_subnet.allocation_pools

    def _list_subnets__fetch_subnets(self, network, kwargs):
        subnets = self.ctl.compute.connection.ex_list_subnets(**kwargs)
        return [subnet for subnet in subnets if
                subnet.network_id == network.network_id]

    def _delete_network__parse_args(self, network, kwargs):
        kwargs['network_id'] = network.network_id

    def _delete_subnet__parse_args(self, subnet, kwargs):
        kwargs['subnet_id'] = subnet.subnet_id

    def _get_libcloud_network(self, network):
        networks = self.ctl.compute.connection.ex_list_networks()
        for net in networks:
            if net.id == network.network_id:
                return net
        raise NetworkNotFoundError('Network %s with network_id %s' %
                                   (network.title, network.network_id))

    def _get_libcloud_subnet(self, subnet):
        subnets = self.ctl.compute.connection.ex_list_subnets()
        for sub in subnets:
            if sub.id == subnet.subnet_id:
                return sub
        raise SubnetNotFoundError('Subnet %s with subnet_id %s' %
                                  (subnet.title, subnet.subnet_id))
