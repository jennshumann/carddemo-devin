import * as cdk from 'aws-cdk-lib/core';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { CardDemoStack } from '../lib/infra-stack';

const template = Template.fromStack(new CardDemoStack(new cdk.App(), 'TestStack'));

test('Aurora PostgreSQL Serverless v2 cluster', () => {
  template.hasResourceProperties('AWS::RDS::DBCluster', {
    Engine: 'aurora-postgresql',
    StorageEncrypted: true,
    ServerlessV2ScalingConfiguration: { MinCapacity: 0.5, MaxCapacity: 2 },
  });
  template.hasResourceProperties('AWS::RDS::DBInstance', { DBInstanceClass: 'db.serverless' });
});

test('encrypted, private S3 data bucket', () => {
  template.hasResourceProperties('AWS::S3::Bucket', {
    BucketEncryption: {
      ServerSideEncryptionConfiguration: [{ ServerSideEncryptionByDefault: { SSEAlgorithm: 'AES256' } }],
    },
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
  });
});

test('Python 3.12 batch Lambda in the VPC', () => {
  template.hasResourceProperties('AWS::Lambda::Function', {
    Runtime: 'python3.12',
    Handler: 'handler.handler',
    VpcConfig: {},
  });
});

test('Aurora Data API enabled for schema management', () => {
  template.hasResourceProperties('AWS::RDS::DBCluster', { EnableHttpEndpoint: true });
});

test('account table DDL applied through the Data API', () => {
  const customResources = JSON.stringify(template.findResources('Custom::AWS'));
  expect(customResources).toContain('CREATE TABLE IF NOT EXISTS account');
  expect(customResources).toContain('ExecuteStatement');
});

test('CBACT01C Lambda reads in/CBACT01C/ and writes out/CBACT01C/', () => {
  template.hasResourceProperties('AWS::Lambda::Function', {
    Runtime: 'python3.12',
    Handler: 'handler.handler',
    Environment: { Variables: { DATA_BUCKET: Match.anyValue() } },
  });
  const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'));
  expect(policies).toContain('/in/CBACT01C/*');
  expect(policies).toContain('/out/CBACT01C/*');
});

test('CBACT04C Lambda reads in/CBACT04C/ and writes out/CBACT04C/', () => {
  const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'));
  expect(policies).toContain('/in/CBACT04C/*');
  expect(policies).toContain('/out/CBACT04C/*');
});

test('CBACT04C Lambda can read its own out/CBACT04C/ (account feedback)', () => {
  const statements = Object.values(template.findResources('AWS::IAM::Policy')).flatMap(
    (p: any) => p.Properties.PolicyDocument.Statement,
  );
  const reads = statements.filter((s: any) => [].concat(s.Action).includes('s3:GetObject*' as never));
  expect(reads.some((s: any) => JSON.stringify(s.Resource).includes('/out/CBACT04C/*'))).toBe(true);
});

test('INTCALC state machine mirrors STEP15 and fails on abend', () => {
  template.resourceCountIs('AWS::StepFunctions::StateMachine', 1);
  const machines = template.findResources('AWS::StepFunctions::StateMachine');
  const definition = JSON.stringify(Object.values(machines)[0].Properties.DefinitionString);
  expect(definition).toContain('STEP15-CBACT04C');
  expect(definition).toContain('INTCALC-ABEND');
  expect(definition).toContain('INTCALC-OK');
});
