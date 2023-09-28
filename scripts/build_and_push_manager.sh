aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin 349229516285.dkr.ecr.eu-west-1.amazonaws.com

docker build --platform linux/x86_64 -t ezrule-manager -f Dockerfile.manager .

docker tag ezrule-manager:latest 349229516285.dkr.ecr.eu-west-1.amazonaws.com/ezrule-manager:latest

docker push 349229516285.dkr.ecr.eu-west-1.amazonaws.com/ezrule-manager:latest