# POC With Lambda, SSM, and Lightsail

## Context

The rootski postgres database has been exposed publicly for some time.
While the database has been protected with a username/password, it is still
vulerable to attacks since the world can reach the database.

We wanted to secure the database by blocking all traffic to the database lightsail
instance from the outside world. Specifically, we wanted only the lambda function
to be able to access the database.

We attempted to give our backend Lambda function and our database lightsail instance
contact with each other by adding a "VPC Peer Connection" to the lightsail VPC
and the default VPC in us-west-2.

At the hackathon, we enabled the VPC Peer Connection and deployed the lambda into
the default VPC, only to discover that when you do that, lambda functions lose
their internet access! (unless you pay $400+/year for a NAT Gateway for your default VPC).

The behavior we observed was that, deployed into the default VPC, the lambda function
hung and timed out with no logs.

Dismayed, we decided to do a proof of concept to investigate whether it is possible
in general to achieve private peered network access with a lambda function and a
lightsail instance... and we did it!

## Problem

There are three services our lambda function needs to be able to access:

1. The postgres database running on a lightsail instance
2. AWS SSM parameter store to read configuration such as the database credentials
3. AWS Cognito to fetch the "JSON Web Keys" which are used to validate JWT tokens

## Solution

### 1. Accessing Lightsail by a private IP Address

First, we created a VPC connection with the lightsail VPC in us-west-2, and the Default VPC in us-west-2.

The CDK code in this POC creates a lightsail instance with a webserver (nginx) running on port 80.
This CDK code also creates a lambda function deployed into the Default VPC. It makes two requests to lightsail
where it tries to access the lightsail instance with the instance's:

1. public IP address, and it FAILS! This is expected, because the lambda has no public internet access.
2. private IP address, and it WORKS! This is expected, because the lambda's VPC is peered with the lightsail VPC.

SUCCESS! We should be able to place a firewall rule on the lightsail instance block any incoming
traffic coming from IP addresses the CIDR range `172.0.0.0/8` AKA "any IP address starting with `172`" or,
said differently, *only clients on the same network as the lightsail instance* 🎉 🎉.

### 2. SSM VPC Endpoint

It turns out that most/all AWS services are accessed by publicly exposed endpoints.
So, for example, if you use `boto3` to try to read a parameter from SSM, `boto3` reaches
out to the public SSM endpoint hosted by AWS.

Here's the problem, since our lambda function didn't have access to the public internet,
it couldn't reach the *any* publicly accessible endpoints, let alone the public SSM endpoint.
It turns out, AWS has a solution called "VPC Endpoints" which allow you to enable services
inside a VPC to reach certain AWS services without the requests needing to leave your VPC!

In this POC, we "created" (enabled) the VPC Endpoint for the SSM service the default VPC of us-west-2,
and we had lambda try to read a SSM parameter. It works!

### 3. Cognito JWT Keys

Unfortunately, AWS doesn't let you create a VPC endpoint for AWS Cognito. So our lambda won't
be able to access cognito to request the service. But this could be okay!

Our *API Gateway* in charge of invoking our backend API lambda function *can* access Cognito.
We can have API Gateway validate tokens *before they are even passed to the lambda*.
Unauthenticated requests will simply never make it to our backend code.

The API Gateway will reject requests to auth-protected endpoints like `POST /breakdown` if there is no
valid JWT token from our cognito user pool in the headers.

This means our API code in the lambda function will not need to reach out to Cognito to download the
keys. Instead, it will simply trust that all tokens are valid, and use the contents to identify the
user.

## Conclusion

It's sad that our lambda does not have internet access when in the Default VPC, but this is by
far the best solution to protect the backend database. This is important because the database
stores email addresses which are PII data. We can't leak those!

Here are the considerations we will need to make with rootski now:

1. The backend API code can only reach services that are in the lightsail VPC or
   on a list of AWS services that support VPC endpoints.
2. We will need to register our backend API endpoints in the API Gateway. Here,
   we will explicitly require certain endpoints to be authenticated, and others
   simply passed through to the backend. [EDIT] This won't actually work because
   of the `GET /breakdowns` endpoint. `GET /breakdowns` does not require auth,
   but it behaves differently if the user *is* authenticated. This means that

   1. we need to write a special lambda authorizer for this endpoint that
      allows the request to reach the backend if either of these conditions are met:

      - there is no token in the headers (request is not even claiming to be authenticated)
      - there is a token in the headers and the token is valid

   2. we need to allow the backend API to get the JWKs another way,
      maybe by writing a CRON Lambda that saves the JWKs to SSM daily.
