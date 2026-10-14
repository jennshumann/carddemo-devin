#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { CardDemoStack } from '../lib/infra-stack';

const app = new cdk.App();
new CardDemoStack(app, 'CardDemoStack', {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION },
});
