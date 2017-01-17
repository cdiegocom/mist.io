import re
import uuid
import netaddr
import mongoengine as me

from mist.io.exceptions import RequiredParameterMissingError

from mist.io.clouds.models import Cloud
from mist.io.clouds.models import CLOUDS

from mist.io.networks.controllers import SubnetController
from mist.io.networks.controllers import NetworkController


# Automatically populated mappings of all Network and Subnet subclasses,
# keyed by their provider name.
NETWORKS, SUBNETS = {}, {}


def _populate_class_mapping(mapping, class_suffix, base_class):
    """Populates a dict that matches a provider name with its model class."""
    for key, value in globals().items():
        if key.endswith(class_suffix) and key != class_suffix:
            if issubclass(value, base_class) and value is not base_class:
                for provider, cls in CLOUDS.items():
                    if key.replace(class_suffix, '') in repr(cls):
                        mapping[provider] = value


class Network(me.Document):
    """The basic Network model.

    This class is only meant to be used as a basic class for cloud-specific
    `Network` subclasses.

    `Network` contains all common, provider-independent fields and handlers.
    """

    id = me.StringField(primary_key=True, default=lambda: uuid.uuid4().hex)
    network_id = me.StringField()

    cloud = me.ReferenceField(Cloud, required=True)
    title = me.StringField()
    description = me.StringField()

    extra = me.DictField()  # The `extra` dictionary returned by libcloud.

    meta = {
        'allow_inheritance': True,
        'collection': 'networks',
        'indexes': [
            {
                'fields': ['cloud', 'network_id'],
                'sparse': False,
                'unique': True,
                'cls': False,
            },
        ],
    }

    def __init__(self, *args, **kwargs):
        super(Network, self).__init__(*args, **kwargs)
        # Set `ctl` attribute.
        self.ctl = NetworkController(self)
        # Calculate and store network type specific fields.
        self._network_specific_fields = [field for field in type(self)._fields
                                         if field not in Network._fields]

    @classmethod
    def add(cls, cloud, name='', description='', object_id='', **kwargs):
        """Add a Network.

        This is a class method, meaning that it is meant to be called on the
        class itself and not on an instance of the class.

        You're not meant to be calling this directly, but on a network subclass
        instead like this:

            network = AmazonNetwork.add(cloud=cloud, name='Ec2Network')

        :param cloud: the Cloud on which the network is going to be created.
        :param name: the name to be assigned to the new network.
        :param description: an optional description.
        :param object_id: a custom object id, passed in case of a migration.
        :param kwargs: the kwargs to be passed to the corresponding controller.

        """
        assert isinstance(cloud, Cloud)
        network = cls(cloud=cloud, title=name, description=description)
        if object_id:
            network.id = object_id
        network.ctl.create(**kwargs)
        return network

    def clean(self):
        """Checks the CIDR to determine if it maps to a valid IPv4 network."""
        if 'cidr' in self._network_specific_fields:
            try:
                netaddr.cidr_to_glob(self.cidr)
            except (TypeError, netaddr.AddrFormatError) as err:
                raise me.ValidationError(err)

    def as_dict(self):
        """Returns the API representation of the `Network` object."""
        net_dict = {
            'id': self.id,
            'network_id': self.network_id,
            'cloud': self.cloud.id,
            'name': self.title,
            'description': self.description,
            'extra': self.extra
        }
        net_dict.update(
            {key: getattr(self, key) for key in self._network_specific_fields}
        )
        return net_dict

    def __str__(self):
        return '%s "%s" (%s)' % (self.__class__.__name__, self.title, self.id)


class AmazonNetwork(Network):
    cidr = me.StringField(required=True)
    default = me.BooleanField(default=False)
    instance_tenancy = me.StringField(default='default', choices=('default',
                                                                  'private'))


class GoogleNetwork(Network):
    cidr = me.StringField()
    mode = me.StringField(default='legacy', choices=('legacy', 'auto',
                                                     'custom'))
    gateway_ip = me.StringField()

    def clean(self):
        """Custom validation for GCE Networks.

        GCE enforces:

            - Regex constrains on network names.
            - CIDR assignment only if `legacy` mode has been selected.

        """
        if self.mode == 'legacy':
            super(GoogleNetwork, self).clean()
        elif self.cidr is not None:
            raise me.ValidationError('CIDR cannot be set for modes other '
                                     'than "legacy"')

        regex = re.compile('^(?:[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?)$')
        if not self.title or not regex.match(self.title):
            raise me.ValidationError('A **lowercase** title must be specified')


class OpenStackNetwork(Network):
    shared = me.BooleanField(default=False)
    admin_state_up = me.BooleanField(default=True)
    router_external = me.BooleanField(default=False)


class Subnet(me.Document):
    """The basic Subnet model.

    This class is only meant to be used as a basic class for cloud-specific
    `Subnet` subclasses.

    `Subnet` contains all common, provider-independent fields and handlers.
    """

    id = me.StringField(primary_key=True, default=lambda: uuid.uuid4().hex)
    subnet_id = me.StringField()

    network = me.ReferenceField('Network', required=True,
                                reverse_delete_rule=me.CASCADE)

    cidr = me.StringField(required=True)
    title = me.StringField()
    description = me.StringField()

    extra = me.DictField()  # The `extra` dictionary returned by libcloud.

    meta = {
        'allow_inheritance': True,
        'collection': 'subnets',
        'indexes': [
            {
                'fields': ['network', 'subnet_id'],
                'sparse': False,
                'unique': True,
                'cls': False,
            },
        ],
    }

    def __init__(self, *args, **kwargs):
        super(Subnet, self).__init__(*args, **kwargs)
        # Set `ctl` attribute.
        self.ctl = SubnetController(self)
        # Calculate and store subnet type specific fields.
        self._subnet_specific_fields = [field for field in type(self)._fields
                                        if field not in Subnet._fields]

    @classmethod
    def add(cls, network, cidr, name='', description='', object_id='',
            **kwargs):
        """Add a Subnet.

        This is a class method, meaning that it is meant to be called on the
        class itself and not on an instance of the class.

        You're not meant to be calling this directly, but on a network subclass
        instead like this:

            subnet = AmazonSubnet.add(network=network,
                                      name='Ec2Subnet',
                                      cidr='172.31.10.0/24')

        :param network: the Network nn which the subnet is going to be created.
        :param cidr: the CIDR to be assigned to the new subnet.
        :param name: the name to be assigned to the new subnet.
        :param description: an optional description.
        :param object_id: a custom object id, passed in case of a migration.
        :param kwargs: the kwargs to be passed to the corresponding controller.

        """
        assert isinstance(network, Network)
        if not cidr:
            raise RequiredParameterMissingError('cidr')

        subnet = cls(network=network, cidr=cidr,
                     title=name, description=description)
        if object_id:
            subnet.id = object_id
        subnet.ctl.create(**kwargs)
        return subnet

    def clean(self):
        """Checks the CIDR to determine if it maps to a valid IPv4 network."""
        try:
            netaddr.cidr_to_glob(self.cidr)
        except (TypeError, netaddr.AddrFormatError) as err:
            raise me.ValidationError(err)

    def as_dict(self):
        """Returns the API representation of the `Subnet` object."""
        subnet_dict = {
            'id': self.id,
            'subnet_id': self.subnet_id,
            'cloud': self.network.cloud.id,
            'network': self.network.id,
            'name': self.title,
            'cidr': self.cidr,
            'description': self.description,
            'extra': self.extra
        }
        subnet_dict.update(
            {key: getattr(self, key) for key in self._subnet_specific_fields}
        )
        return subnet_dict

    def __str__(self):
        return '%s "%s" (%s)' % (self.__class__.__name__, self.title, self.id)


class AmazonSubnet(Subnet):
    availability_zone = me.StringField(required=True)


class GoogleSubnet(Subnet):
    region = me.StringField(required=True)
    gateway_ip = me.StringField()

    def clean(self):
        """Extended validation for GCE Subnets."""
        regex = re.compile('^(?:[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?)$')
        if not self.title or not regex.match(self.title):
            raise me.ValidationError('A **lowercase** title must be specified')
        super(GoogleSubnet, self).clean()

class OpenStackSubnet(Subnet):
    gateway_ip = me.StringField()
    ip_version = me.IntField(default=4)
    enable_dhcp = me.BooleanField(default=True)
    dns_nameservers = me.ListField(default=lambda: [])
    allocation_pools = me.ListField(default=lambda: [])


_populate_class_mapping(NETWORKS, 'Network', Network)
_populate_class_mapping(SUBNETS, 'Subnet', Subnet)
