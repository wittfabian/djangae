# Environment

You can detect things about your running environment by using the utility functions
located in djangae.environment.

## djangae.environment.is_production_environment()

Returns if the request is currently running on the live GAE servers

## djangae.environment.is_development_environment()

Returns whether or not the code is running on the local development environment

## djangae.environment.application_id()

Returns the application id from app.yaml (or wherever the code is deployed)

## djangae.environment.get_application_root()

Returns the root folder of your application (this is the folder containing app.yaml)

## djangae.environment.task_name()

Returns the current task name if the code is running on a task queue

## djangae.environment.task_queue_name()

Returns the current task queue name if the code is running on a task queue

## djangae.environment.is_in_task()

Returns true if the code is running in a task on the task queue

## djangae.environment.task_retry_count()

Returns the number of times the task has retried, or 0 if the code is not
running on a queue
