#!/bin/bash

# Check if the parameters are provided
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Error: Both file prefix and environment arguments are required."
  exit 1
fi

file_prefix="$1"
environment="$2"
stack_name="${file_prefix//_/-}-${environment}"
template_file="deployment/aws/${file_prefix}.yaml"

export AWS_DEFAULT_REGION=eu-west-1

echo "Checking if stack $stack_name exists..."

if aws cloudformation describe-stacks --stack-name "$stack_name" >/dev/null 2>&1; then
  echo "Stack $stack_name exists, updating..."
  aws cloudformation update-stack --stack-name "$stack_name" --template-body "file://$template_file" --capabilities CAPABILITY_NAMED_IAM --parameters ParameterKey=Environment,ParameterValue="$environment"
  echo "Stack update initiated."
  aws cloudformation wait stack-update-complete --stack-name "$stack_name"
  echo "Stack update complete."
else
  echo "Stack $stack_name does not exist, creating..."
  aws cloudformation create-stack --stack-name "$stack_name" --template-body "file://$template_file" --capabilities CAPABILITY_NAMED_IAM --parameters ParameterKey=Environment,ParameterValue="$environment"
  echo "Stack creation initiated."
  aws cloudformation wait stack-create-complete --stack-name "$stack_name"
  echo "Stack creation complete."
fi
