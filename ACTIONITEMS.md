# Overview

You must build a connector in Python that periodically fetches files from the Autodesk Construction Cloud API and Google Drive API, gets the file link, title, date created, date updated, project id and user id, and pushes it to a (mock for now) supabase table. This action will be run every 5 minutes for each enumerated endpoint, and it must only fetch files that have not been pushed to the supabase table yet, based on the created and updated timestamp. 

The endpoints should be initially given in a data array, which has objects (hashmaps) for the endpoint type + endpoint details + project id + user id. It should do a scheduled fetch for each endpoint, in parallel. This should be ran on a cloud service provider.

It should be the foundation of a feature implemented in a SaaS. Therefore, room must be made for adding new endpoints and schedules.

First, write a task plan to complete this in this ACTIONITEMS.md file. Then, run the tasks.

## Task 3: API Client - Google Drive
- Implement Google Drive API client
- Set up authentication (service account or OAuth)
- Create methods to list and fetch file metadata
- Handle pagination and rate limiting
- Extract required file information (link, title, dates, etc.)

## Task 4: API Client - Autodesk Construction Cloud
- Implement Autodesk Construction Cloud API client
- Set up authentication (OAuth 2.0)
- Create methods to list and fetch file metadata
- Handle pagination and rate limiting
- Extract required file information

## Task 5: Core Connector Logic
- Create abstract base class for API connectors
- Implement file synchronization logic
- Add timestamp-based filtering to avoid duplicates
- Create unified file metadata model
- Handle error cases and retries

## Task 6: Configuration Management
- Create endpoint configuration schema
- Implement configuration loading from JSON/YAML
- Support for multiple endpoints with different schedules
- Environment variable support for sensitive data

## Task 7: Scheduling System
- Implement scheduler that runs every 5 minutes per endpoint
- Add parallel processing for multiple endpoints
- Create job queue system
- Add monitoring and health checks

## Task 8: Parallel Processing & Performance
- Implement asyncio for concurrent API calls
- Add connection pooling
- Optimize batch processing
- Add performance metrics and logging

## Task 9: Cloud Deployment Setup
- Create Dockerfile for containerization
- Set up deployment configuration (Docker Compose or K8s)
- Add environment variable management
- Create startup scripts and health checks

## Task 10: Testing and Quality Assurance
- Write unit tests for all components
- Create integration tests with mock APIs
- Add end-to-end testing scenarios
- Set up CI/CD pipeline basics

## Task 11: Documentation and Extensibility
- Document API client interfaces
- Create guide for adding new connectors
- Document configuration options
- Add README with setup instructions