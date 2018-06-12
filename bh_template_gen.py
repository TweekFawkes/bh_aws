#!/usr/bin/python
# -*- coding: utf-8 -*-
# Converted from VPC_With_VPN_Connection.template located at:
# http://aws.amazon.com/cloudformation/aws-cloudformation-templates

#Useful references found here:
# https://github.com/cloudtools/troposphere/blob/master/examples/ApplicationELB.py
# http://boto3.readthedocs.io/en/latest/reference/services/elbv2.html#ElasticLoadBalancingv2.Client.create_target_group
# https://github.com/cloudtools/troposphere/blob/master/examples/Lambda.py

from troposphere import Base64, FindInMap, GetAtt, Join, Output
from troposphere import Parameter, Ref, Tags, Template
from troposphere.ec2 import Route, \
    VPCGatewayAttachment, SubnetRouteTableAssociation, Subnet, RouteTable, \
    VPC, NetworkInterfaceProperty, \
    Instance, InternetGateway, \
    SecurityGroupRule, SecurityGroup, \
    LaunchSpecifications
from troposphere.iam import Role, InstanceProfile
from awacs.aws import Allow, Statement, Principal, Policy
from awacs.sts import AssumeRole


public_instance_userdata = """#!/bin/bash
echo "START" > /tmp/userdata001.txt
id >> /tmp/userdata001.txt
uname -a >> /tmp/userdata001.txt
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
sudo apt-get update
apt-cache policy docker-ce
sudo apt-get install -y docker-ce
"""

private_instance_userdata = """#!/bin/bash
echo "START" > /tmp/userdata001.txt
id >> /tmp/userdata001.txt
uname -a >> /tmp/userdata001.txt
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
sudo apt-get update
apt-cache policy docker-ce
sudo apt-get install -y docker-ce
"""


ami_mapping = {
    "us-east-2": {"AMI": "ami-6a003c0f"},
}


def generate_template(service_name):
    t = Template()
    t.add_version('2010-09-09')

    t.add_description("""\
    AWS CloudFormation Template for AWS Exploitation Lab """)

    t.add_mapping("RegionMap", ami_mapping)

    keyname_param = t.add_parameter(
        Parameter(
            'KeyName',
            ConstraintDescription='must be the name of an existing EC2 KeyPair.',
            Description='Name of an existing EC2 KeyPair to enable SSH access to \
    the instance',
            Type='AWS::EC2::KeyPair::KeyName',
        ))

    sshlocation_param = t.add_parameter(
        Parameter(
            'SSHLocation',
            Description=' The IP address range that can be used to SSH to the EC2 \
    instances',
            Type='String',
            MinLength='9',
            MaxLength='18',
            Default='0.0.0.0/32',
            AllowedPattern="(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})/(\d{1,2})",
            ConstraintDescription=(
                "must be a valid IP CIDR range of the form x.x.x.x/x."),
        ))

    instanceType_param = t.add_parameter(Parameter(
        'InstanceType',
        Type='String',
        Description='WebServer EC2 instance type',
        Default='t2.micro',
        AllowedValues=[
            't2.micro', 't2.small', 't2.medium',
            'm3.medium', 'm3.large', 'm3.xlarge', 'm3.2xlarge',
        ],
        ConstraintDescription='must be a valid EC2 instance type.',
    ))

    ref_stack_id = Ref('AWS::StackId')

    ec2_role = t.add_resource(Role(
        "%sEC2Role" % service_name,
        AssumeRolePolicyDocument=Policy(
            Statement=[
                Statement(
                    Effect=Allow,
                    Action=[AssumeRole],
                    Principal=Principal("Service", ["ec2.amazonaws.com"])
                )
            ]
        )
    ))
    ec2_role.ManagedPolicyArns = [
        "arn:aws:iam::aws:policy/ReadOnlyAccess"
    ]

    VPC_ref = t.add_resource(
        VPC(
            'VPC',
            CidrBlock='10.0.0.0/16',
            Tags=Tags(
                Application=ref_stack_id)))

    instanceProfile = t.add_resource(
        InstanceProfile(
            "InstanceProfile",
            InstanceProfileName="%sInstanceRole" % (service_name),
            Roles=[Ref(ec2_role)]))

    public_subnet = t.add_resource(
        Subnet(
            '%sSubnetPublic' % service_name,
            MapPublicIpOnLaunch=True,
            CidrBlock='10.0.1.0/24',
            VpcId=Ref(VPC_ref),
            Tags=Tags(
                Application=ref_stack_id,
                Name="%sSubnet_public" % (service_name))
        )
    )

    private_subnet = t.add_resource(
        Subnet(
            '%sSubnetPrivate' % service_name,
            MapPublicIpOnLaunch=False,
            CidrBlock='10.0.2.0/24',
            VpcId=Ref(VPC_ref),
            Tags=Tags(
                Application=ref_stack_id,
                Name="%sSubnet_private" % (service_name))
        )
    )

    internetGateway = t.add_resource(
        InternetGateway(
            'InternetGateway',
            Tags=Tags(
                Application=ref_stack_id,
                Name="%sInternetGateway" % service_name)))

    gatewayAttachment = t.add_resource(
        VPCGatewayAttachment(
            'AttachGateway',
            VpcId=Ref(VPC_ref),
            InternetGatewayId=Ref(internetGateway)))

    routeTable = t.add_resource(
        RouteTable(
            'RouteTable',
            VpcId=Ref(VPC_ref),
            Tags=Tags(
                Application=ref_stack_id,
                Name="%sRouteTable" % service_name)))

    route = t.add_resource(
        Route(
            'Route',
            DependsOn='AttachGateway',
            GatewayId=Ref('InternetGateway'),
            DestinationCidrBlock='0.0.0.0/0',
            RouteTableId=Ref(routeTable),
        ))

    # Only associate this Route Table with the public subnet
    subnetRouteTableAssociation = t.add_resource(
        SubnetRouteTableAssociation(
            'SubnetRouteTableAssociation',
            SubnetId=Ref(public_subnet),
            RouteTableId=Ref(routeTable),
        ))

    instanceSecurityGroup = t.add_resource(
        SecurityGroup(
            'InstanceSecurityGroup',
            GroupDescription='%sSecurityGroup' % service_name,
            SecurityGroupIngress=[
                SecurityGroupRule(
                    IpProtocol='tcp',
                    FromPort='22',
                    ToPort='22',
                    CidrIp=Ref(sshlocation_param)),
                SecurityGroupRule(
                    IpProtocol='tcp',
                    FromPort='80',
                    ToPort='80',
                    CidrIp='0.0.0.0/0'),
                SecurityGroupRule(
                    IpProtocol='tcp',
                    FromPort='443',
                    ToPort='443',
                    CidrIp='0.0.0.0/0'),
                SecurityGroupRule(
                    IpProtocol='tcp',
                    FromPort='0',
                    ToPort='65535',
                    CidrIp="10.0.0.0/8"),
            ],
            VpcId=Ref(VPC_ref),
        )
    )

    public_instance = t.add_resource(
        Instance(
            "Public%sInstance" % service_name,
            ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "AMI"),
            InstanceType=Ref(instanceType_param),
            KeyName=Ref(keyname_param),
            NetworkInterfaces=[
                NetworkInterfaceProperty(
                    GroupSet=[
                        Ref(instanceSecurityGroup)],
                    AssociatePublicIpAddress='true',
                    DeviceIndex='0',
                    DeleteOnTermination='true',
                    SubnetId=Ref(public_subnet))],
            UserData=Base64(public_instance_userdata),
            Tags=Tags(
                Application=ref_stack_id,
                Name='%sPublicInstance' % (service_name)),
            IamInstanceProfile="%sInstanceRole" % (service_name)
        )
    )

    private_instance = t.add_resource(
        Instance(
            "Private%sInstance" % service_name,
            ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "AMI"),
            InstanceType=Ref(instanceType_param),
            KeyName=Ref(keyname_param),
            NetworkInterfaces=[
                NetworkInterfaceProperty(
                    GroupSet=[
                        Ref(instanceSecurityGroup)],
                    DeviceIndex='0',
                    DeleteOnTermination='true',
                    SubnetId=Ref(private_subnet))],
            UserData=Base64(private_instance_userdata),
            Tags=Tags(
                Application=ref_stack_id,
                Name='%sPrivateInstance' % (service_name)),
            IamInstanceProfile="%sInstanceRole" % (service_name)
        )
    )
    return t.to_json()


def lambda_handler(event, context):
    # Prep the AZ & Region info for mapping
    # This is required because you can't iterate over AZs within a template.

    # input_region = raw_input("Specify AWS Region: ")
    # input_region = "us-east-1"
    service_name = "bluelizard"
    template = generate_template(service_name)
    outfile = "bh_template.json"
    output = open(outfile, "w+")
    output.write(template)
    print "Wrote to %s" % outfile
    output.close()

lambda_handler(None, None)