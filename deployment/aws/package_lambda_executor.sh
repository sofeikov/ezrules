if [ -z "$EZRULES_BUCKET" ]
then
    echo "EZRULES_BUCKET env is not set"
    exit 1
fi
docker run -v "$PWD":/var/task "public.ecr.aws/sam/build-python3.8:latest-x86_64" /bin/sh -c "yum install -y libxml2 libxslt && pip install --target /var/task/package -r requirements.txt"

cd package
zip -r ../deployment_package.zip .
cd ..

zip deployment_package.zip backend/rule_executors/lambda_rule_executor.py -j
zip -r deployment_package.zip backend
zip -r deployment_package.zip core

aws s3 cp deployment_package.zip s3://${EZRULES_BUCKET}/lambda/

rm deployment_package.zip
rm -rf package