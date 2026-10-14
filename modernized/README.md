# CardDemo modernized (AWS)

COBOL batch programs from `/app` re-implemented as AWS Lambda functions (Python 3.12), with data in Aurora PostgreSQL Serverless v2 and files in S3. `/app` is the read-only source of truth.

- `infra/` — AWS CDK app (TypeScript). `npm install && npx cdk synth`, `npm test`.
- `lambdas/` — one directory per Lambda function.
