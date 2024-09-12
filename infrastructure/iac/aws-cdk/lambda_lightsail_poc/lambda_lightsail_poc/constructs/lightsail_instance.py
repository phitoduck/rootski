from textwrap import dedent

import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk import aws_lightsail as lightsail
from constructs import Construct

LIGHTSAIL_USER_DATA_SCRIPT: str = dedent(
    """\
#!/bin/bash

set -x

# act as the super user for this script
sudo su

# map python -> python2 (yum needs python2)
unlink /usr/bin/python
ln -sfn /usr/bin/python2 /usr/bin/python

# update and install docker
# NOTE, -y makes yum answer yes to all prompts
# httpd-tools is for bcrypt via the htpasswd command for generating basic auth passwords for the /docs and traefik UIs
yum update -y
yum -y install docker git httpd-tools zsh
usermod -a -G docker ec2-user # allow ec2-user to use docker commands

# install docker-compose and make the binary executable
curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m) -o /usr/bin/docker-compose
chmod +x /usr/bin/docker-compose

# install ohmyzsh
sh -c "$(wget https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -) --unattended"

# start docker
service docker start

cat << EOF > /tmp/docker-compose.yml
version: "3.9"

# run a basic webserver on port 80 to test network connectivity
services:
    nginx:
        image: nginx
        ports:
            - 80:80
        deploy:
            labels:
                traefik.enable: "false"
            replicas: 1

EOF

docker swarm init
docker stack deploy -c /tmp/docker-compose.yml nginx
"""
)


class LightsailInstance(Construct):
    def __init__(self, scope: cdk.Stack, construct_id: str, name_prefix: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        self.instance = lightsail.CfnInstance(
            self,
            id=name_prefix + "lightsail-instance-for-vpc-lambda",
            instance_name="lightsail-instance-for-vpc-lambda",
            key_pair_name="rootski.id_rsa",
            availability_zone="us-west-2a",
            networking=lightsail.CfnInstance.NetworkingProperty(
                ports=[
                    lightsail.CfnInstance.PortProperty(
                        access_direction="inbound",
                        cidrs=["0.0.0.0/0"],
                        common_name="SSH",
                        from_port=22,
                        protocol="tcp",
                        to_port=22,
                    ),
                    lightsail.CfnInstance.PortProperty(
                        access_direction="inbound",
                        cidrs=["0.0.0.0/0"],
                        common_name="Postgres",
                        from_port=8000,
                        protocol="tcp",
                        to_port=8000,
                    ),
                    # traefik
                    lightsail.CfnInstance.PortProperty(
                        access_direction="inbound",
                        cidrs=["0.0.0.0/0"],
                        common_name="Postgres",
                        from_port=80,
                        protocol="tcp",
                        to_port=80,
                    ),
                    lightsail.CfnInstance.PortProperty(
                        access_direction="outbound",
                        cidrs=["0.0.0.0/0"],
                        common_name="All Outbound Traffic",
                        from_port=0,
                        protocol="all",
                        to_port=65535,
                    ),
                ]
            ),
            # found using 'aws lightsail get-blueprints --profile rootski'
            blueprint_id="amazon_linux_2",
            # found using 'aws lightsail get-bundles --profile rootski'
            bundle_id="micro_2_0",
            user_data=LIGHTSAIL_USER_DATA_SCRIPT,
        )

        # free as long as the instance is running
        self.static_ip = lightsail.CfnStaticIp(
            self,
            id="Rootski-DB-Lightsail-StaticIp",
            static_ip_name=name_prefix + "Rootski-DB-Lightsail-StaticIp",
            attached_to=self.instance.ref,
        )


if __name__ == "__main__":

    class LightsailStack(Stack):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.lightsail_instance = LightsailInstance(self, "test-instance")

    app = cdk.App()
    stack = LightsailStack(app, "test-stack")
    instance = stack.lightsail_instance

    print(instance.instance.user_data)
