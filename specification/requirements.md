# Requirements

This is a twitter clone application that allows users to post messages, follow other users, and interact with posts.

## Functional Requirements

1. Authentication:
    - User must be able to register, log in, and log out.
    - Password and email must be the only required login method.
    - This must protect private routes and user data.

2. User Profile Management:
    - Users must be able to view and edit their profile information.
    - Minimal user information:
        - Name
        - Username
        - Email
        - Profile picture (placeholder image)
        - Bio

3. Tweet Management:
    - Users must be able to create, and delete tweets.
    - Tweets should have a character limit (e.g., 280 characters).
    - Tweets must be able to contain text, images, and links.
    - Users must be able to view a list of tweets from users they follow in an infinite scrolling feed sorted chronologically.

4. Social interactions:
    - Users must be able to follow and unfollow other users.
    - Users must be able to like and unlike tweets.
    - Users must be able to reply to flat reply tweets (no nested replies).
    - Users must be able to view the number of likes and replies on each tweet.
    - Users must be able to view a list of followers and following for each user.
    - Users must be able to view a list of tweets from a specific user.
    - User must be able to search for other users by name or username. Done by exact match, prefix, or fuzzy match.
    - User must receive instant notifications for new followers, likes, and replies. Delivered within 2s over WebSocket while the recipient is online; persisted for later view if offline.

5. LLM features:
    - Users must be able to generate tweets using LLM.
    - Users must be able to generate summaries of threads using LLM.

## Non-Functional Requirements

1. Performance:
    - The application must be able to handle 100 concurrent users without significant performance degradation. this is a learning/portfolio project, not production scale

2. Security:
    - User passwords must be hashed and salted before storage.
    - The application must implement rate limiting to prevent abuse of the API.
    - The application must protect against common web vulnerabilities (e.g., SQL injection, XSS, CSRF).
    - The application must implement proper access control to ensure users can only access their own data and actions.
    - The application must implement structured logs + error tracking.

3. Scalability:
    - The application must be able to handle a growing number of users and tweets without significant performance degradation. 

4. Usability:
    - The application must have a responsive design that works well on both desktop and mobile devices. The design should be thought of for mobile first and scale up to desktop. Minimum breakpoints: mobile (< 640px), tablet (640–1024px), desktop (> 1024px).
    - The application must provide clear error messages and feedback to users.
    - The application must have an intuitive interface.
    - The application must use animations and transitions to enhance the user experience.

5. Maintainability:
    - The application code must be well-documented and follow best practices for code organization and structure.
    - The application must have a clear separation of concerns between the frontend and backend.
    - The application must have unit, integration, and end-to-end tests to ensure functionality and prevent regressions. The coverage should be at least 80% for the backend and 70% for the frontend.
    - The application must have a clear and consistent coding style and naming conventions.

6. Deployment:
    - The application must have a seed script to populate the database with initial data for testing and development purposes.
    - The application must have a deployment script to automate the deployment process. Makefile or shell script can be used for this purpose.
    - The application must use docker for development and deployment to ensure consistency across environments.
    - The testing must run inside a docker container to ensure consistency across environments.
    - The testing framework must be set up to run tests in a CI/CD pipeline.
    - The application must use version numbering and semantic versioning for releases using git tags.
