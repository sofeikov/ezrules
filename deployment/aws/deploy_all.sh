env=$1

./deployment/aws/deploy_stack.sh ezrules_bucket_stack ${env}
./deployment/aws/deploy_stack.sh ezrules_dynamodb_stack ${env}
./deployment/aws/deploy_stack.sh ezrules_app_stack ${env}