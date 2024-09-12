import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class SsmVpcEndpoint(Construct):
    def __init__(self, scope: cdk.Stack, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        default_vpc = ec2.Vpc.from_lookup(
            self, construct_id + "Vpc-Endpoint-Default-VPC", vpc_name="Default VPC"
        )

        self.ssm_endpoint_security_group = ec2.SecurityGroup(
            self,
            construct_id + "SSM-VPC-Endpoint-SG",
            allow_all_outbound=True,
            vpc=default_vpc,
            description="Allow any service to hit the internal SSM endpoint.",
        )

        self.ssm_endpoint_security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(), connection=ec2.Port.all_tcp(), description="Enable all inbound traffic"
        )

        self.ssm_endpoint = ec2.InterfaceVpcEndpoint(
            self,
            construct_id + "SSM-VPC-Endpoint",
            # enable the DNS in the subnets to resolve the endpoint FQDN to the IP of the AWS service
            private_dns_enabled=True,
            vpc=default_vpc,
            service=ec2.InterfaceVpcEndpointAwsService.SSM,
            # the default VPC only has one subnet per AZ, so this will make the private SSM endpoint available in every subnet
            subnets=ec2.SubnetSelection(one_per_az=True),
            security_groups=[self.ssm_endpoint_security_group],
        )
