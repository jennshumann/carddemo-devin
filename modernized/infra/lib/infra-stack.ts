import * as fs from 'fs';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cr from 'aws-cdk-lib/custom-resources';
import { Construct } from 'constructs';

export class CardDemoStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Isolated subnets only (no NAT); AWS services reached via VPC endpoints.
    const vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [{ name: 'isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED }],
    });
    vpc.addGatewayEndpoint('S3Endpoint', { service: ec2.GatewayVpcEndpointAwsService.S3 });
    vpc.addInterfaceEndpoint('SecretsManagerEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
    });

    const dataBucket = new s3.Bucket(this, 'DataBucket', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    const db = new rds.DatabaseCluster(this, 'Database', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_17_9,
      }),
      writer: rds.ClusterInstance.serverlessV2('writer'),
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 2,
      credentials: rds.Credentials.fromGeneratedSecret('carddemo_admin'),
      defaultDatabaseName: 'carddemo',
      enableDataApi: true,
      storageEncrypted: true,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
    });

    const batchFn = new lambda.Function(this, 'BatchSkeletonFn', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../lambdas/batch_skeleton')),
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      environment: {
        DATA_BUCKET: dataBucket.bucketName,
        DB_SECRET_ARN: db.secret!.secretArn,
      },
    });
    dataBucket.grantReadWrite(batchFn);
    db.secret!.grantRead(batchFn);
    db.connections.allowDefaultPortFrom(batchFn);

    // Shared Aurora tables, created through the RDS Data API (one statement each).
    const schemaTables: Array<{ table: string; ddl: string }> = [
      { table: 'account', ddl: '../../CBACT01C/schema/account.sql' },
    ];
    for (const { table, ddl } of schemaTables) {
      const sql = fs.readFileSync(path.join(__dirname, ddl), 'utf8');
      const executeDdl: cr.AwsSdkCall = {
        service: 'rds-data',
        action: 'ExecuteStatement',
        parameters: {
          resourceArn: db.clusterArn,
          secretArn: db.secret!.secretArn,
          database: 'carddemo',
          sql,
        },
        physicalResourceId: cr.PhysicalResourceId.of(`carddemo-table-${table}`),
      };
      const createTable = new cr.AwsCustomResource(this, `Table-${table}`, {
        onCreate: executeDdl,
        onUpdate: executeDdl,
        policy: cr.AwsCustomResourcePolicy.fromSdkCalls({ resources: [db.clusterArn] }),
        installLatestAwsSdk: false,
      });
      db.grantDataApiAccess(createTable);
      createTable.node.addDependency(db);
    }

    // CBACT01C: account extract. Reads in/CBACT01C/, writes out/CBACT01C/.
    const cbact01cFn = new lambda.Function(this, 'Cbact01cFn', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../CBACT01C/src'), {
        exclude: ['__pycache__'],
      }),
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      environment: { DATA_BUCKET: dataBucket.bucketName },
    });
    dataBucket.grantRead(cbact01cFn, 'in/CBACT01C/*');
    dataBucket.grantPut(cbact01cFn, 'out/CBACT01C/*');

    new cdk.CfnOutput(this, 'DataBucketName', { value: dataBucket.bucketName });
    new cdk.CfnOutput(this, 'DbSecretArn', { value: db.secret!.secretArn });
    new cdk.CfnOutput(this, 'BatchSkeletonFnName', { value: batchFn.functionName });
    new cdk.CfnOutput(this, 'Cbact01cFnName', { value: cbact01cFn.functionName });
  }
}
