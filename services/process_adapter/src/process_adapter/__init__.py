"""Process Adapter service for the MFO Appeals Platform.

Isolates the platform from the Flowable REST API and exposes domain-oriented operations. In
TASK_00D this is a technical spike: it validates the start/user-task/timer/message/history loop
without a business process and has no own database.
"""
