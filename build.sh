#!/bin/bash

# Build all services
docker-compose build

# Tag images for ECR
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}

docker tag ecom-product-service:latest ${ECR_REGISTRY}/ecom-product-service:latest
docker tag ecom-user-service:latest ${ECR_REGISTRY}/ecom-user-service:latest
docker tag ecom-order-service:latest ${ECR_REGISTRY}/ecom-order-service:latest
docker tag ecom-cart-service:latest ${ECR_REGISTRY}/ecom-cart-service:latest

# Push to ECR
docker push ${ECR_REGISTRY}/ecom-product-service:latest
docker push ${ECR_REGISTRY}/ecom-user-service:latest
docker push ${ECR_REGISTRY}/ecom-order-service:latest
docker push ${ECR_REGISTRY}/ecom-cart-service:latest
