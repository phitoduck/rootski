"""
App defining an API Gateway and Lambda Function with a FastAPI app.

.. note::

    Eric recommends *never* putting node.try_get_context() calls inside of a stack.
    Hiding those calls inside of a stack makes it very unintuitive to figure out what inputs
    you need to actually create a stack. Instead, write stacks and constructs assuming any
    required inputs will be passed as arguments to the constructor. Make the calls to try_get_context
    in the app.py.

    In each stack/construct, use a dataclass, enum, or constants to define actual string constants
    used for ContextVars (inputs) and Cloudformation Outputs (outputs).
"""

import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from lambda_lightsail_poc.constructs.lightsail_instance import LightsailInstance
from lambda_lightsail_poc.constructs.ping_lambda import PingLambdaFunction
from lambda_lightsail_poc.constructs.ssm_vpc_endpoint import SsmVpcEndpoint


class LambdaLightsailPOCStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        self.vpc_endpoint = SsmVpcEndpoint(
            self,
            "SSM-VPC-Endpoint",
        )

        self.lightsail_instance = LightsailInstance(
            self,
            construct_id="LightsailInstance",
            name_prefix="POC-",
        )

        self.test_ssm_param = ssm.StringParameter(
            self,
            "parameter-for-ping-lambda",
            parameter_name="/lightsail-poc/test-parameter",
            string_value="Hi friends! 😈",
        )

        self.lightsail_lambda_pinger = PingLambdaFunction(
            self,
            construct_id="PingLambdaFunction",
            lightsail_public_ip=self.lightsail_instance.static_ip.attr_ip_address,
            lightsail_private_ip=self.lightsail_instance.instance.attr_private_ip_address,
            test_ssm_parameter=self.test_ssm_param,
        )


if __name__ == "__main__":
    app = cdk.App()

    environment = cdk.Environment(
        account="091910621680",
        region="us-west-2",
    )

    LambdaLightsailPOCStack(
        app,
        "Lambda-Lightsail-POC-Stack-cdk",
        env=environment,
    )

    app.synth()
