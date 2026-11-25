# NeuroLock — Behavioral Biometric Authentication System

## 1. Project Overview

NeuroLock is a behavioral biometric authentication system that uses a user's typing rhythm as an additional layer of identity verification. It combines password-based authentication with typing-pattern analysis to help protect user accounts and restricted resources.

The system captures typing characteristics, such as key dwell time and intervals between keystrokes, and compares the extracted features with the user's enrolled typing profile.

### Main Features

- User registration and login
- Email confirmation and password recovery
- Typing-rhythm biometric enrollment and verification
- Two-factor authentication workflow
- Biometric accuracy feedback
- Security alert emails
- Password-failure lockout and email-based early unlock
- Protected dashboard and file operations
- Supabase database and storage integration

## 2. Technologies Used

- **Frontend:** React, Vite, JavaScript
- **Backend:** Python, FastAPI, Uvicorn
- **Database and Authentication:** Supabase
- **Biometric Analysis:** Python-based typing-rhythm feature comparison
- **Email Notifications:** Gmail SMTP
- **Development Tools:** Visual Studio Code, PowerShell, npm

## 3. System Requirements

Before running NeuroLock, ensure that your computer has:

- Windows 10 or Windows 11
- Python compatible with the project's dependencies
- Node.js and npm
- Internet access for Supabase and email services
- Visual Studio Code or another code editor
- A configured Supabase project and valid application environment variables

## 4. Project Structure

The project contains two main components:

- `backend/` — FastAPI application, authentication endpoints, biometric processing, email alerts, and backend tests.
- `frontend/` — React application, login and registration screens, biometric verification interface, and dashboard.

Other project files may include SQL schema files, environment configuration, dependency manifests, documentation, and test files.

## 5. Installation and Configuration

### Step 1: Open the project

Open the NeuroLock project folder in Visual Studio Code.

Open a terminal and navigate to the backend directory:

```powershell
cd backend
```

### Step 2: Install backend dependencies

Run:

```powershell
py -m pip install -r requirements.txt
```

If the project uses a Python virtual environment, activate it first and install the dependencies inside that environment.

### Step 3: Configure environment variables

Create or configure the backend `.env` file using the project's existing environment-variable template and configuration requirements.

Configure the necessary Supabase URL and keys, authentication settings, biometric threshold, application/API URL, and Gmail SMTP settings.

Keep real secrets private. Do not upload passwords, API keys, service-role keys, or Gmail app passwords to a public repository.

### Step 4: Install frontend dependencies

Open a second terminal and navigate to the frontend directory:

```powershell
cd frontend
npm install
```

Configure the frontend environment variables according to the existing project configuration.

## 6. Running the Application

### Step 1: Start the backend

In the backend terminal, run:

```powershell
py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend should be available at:

- API base URL: `http://127.0.0.1:8000`
- Interactive API documentation: `http://127.0.0.1:8000/docs`
- Health endpoint: `http://127.0.0.1:8000/health`

Keep this terminal open while using the application.

### Step 2: Start the frontend

In the second terminal, navigate to the frontend directory and run:

```powershell
npm run dev
```

Vite will display a local development URL, usually:

`http://localhost:5173`

Open the exact URL shown in the terminal in your browser.

Keep both terminals running while using NeuroLock.

## 7. How to Use NeuroLock

### Step 1: Register an account

Open the application and enter the required registration details. Follow the email-confirmation instructions if confirmation is enabled.

### Step 2: Log in

Enter the registered email address and password. If authentication fails, verify the credentials and account-confirmation status.

### Step 3: Enroll your typing rhythm

If the account has not yet enrolled a typing profile, follow the enrollment interface. Type the requested text naturally and complete the required capture process.

The system uses the captured typing characteristics to establish a baseline profile.

### Typing speed and keystroke analysis

Sign in and open **Typing analysis** to take a three-prompt test using the same
phrases as enrollment. Start each sample before typing; pasted and dropped text
is blocked. Incomplete attempts are reported as incomplete and do not receive a
sample or overall keystroke score. A fully timed attempt with typing errors is
still analyzed and its character accuracy reduces the score. Retake an
incomplete sample or restart the test to try again.

The analysis uses browser keydown/keyup timestamps. WPM is final typed
characters divided by five, scaled by elapsed time from the first printable
keydown to the final captured key event. Accuracy is the number of matching
characters (using sequence alignment) divided by the longer of the expected and
entered text. Dwell is the average duration of printable keys; inter-key latency
is the gap from one printable keyup to the next printable keydown. Rhythm
consistency is `100 / (1 + coefficient of variation of inter-key latency)`.

The 0–100 keystroke score is deliberately independent of speed:

- 40% final-text accuracy.
- 30% within-sample rhythm consistency.
- 30% consistency of mean dwell and mean inter-key latency across the three
  samples, each measured as `100 / (1 + coefficient of variation)`.

The overall score is the mean of the three per-sample scores. The consistency
summary calls a between-sample score of 85 or above "very consistent," 70–84.99
"fairly consistent," and lower scores "varied." These transparent weights are
a descriptive prototype, not a scientifically validated biometric classifier.
If an enrolled template exists, the page also reports the existing
feature-distance comparison as a separate prototype similarity; it is not an
identity probability, proof of identity, or a score based on typing speed. If no
template exists, the page prompts you to complete enrollment instead.

The authenticated `POST /api/typing-analysis` endpoint validates the three
attempts and calculates the metrics server-side. Event traces are used only for
the request and are not written to Supabase or stored in a new database table.
The existing enrollment template and authentication endpoints are unchanged.

### Step 4: Complete biometric verification

After password authentication, complete the typing-rhythm verification requested by the application.

The backend compares the submitted typing features with the enrolled profile. Access to protected resources should be granted only when the required verification succeeds.

### Step 5: Access the dashboard

After successful authentication and required biometric verification, use the dashboard to access the features available to your account.

### Step 6: Receive security notifications

NeuroLock can send application security alerts through its configured Gmail SMTP service. Email delivery depends on valid SMTP configuration and network availability.

### Step 7: Handle login lockout

If repeated password failures trigger a lockout, follow the instructions in the lockout email if the early-unlock feature is configured. Otherwise, wait for the configured lockout period to expire.

Biometric failure alerts and biometric lockout behavior depend on the implemented version of the project.

## 8. Password Recovery

Use the password-recovery option on the login screen and follow the instructions sent to your registered email address.

Password recovery and account lockout are separate processes. Resetting a password does not necessarily clear an authentication-failure counter.

## 9. Troubleshooting

**Backend fails to start**

- Check that the terminal is in the `backend` directory.
- Confirm that the required Python packages are installed.
- Verify that the Python environment being used is the one where the dependencies were installed.
- Read the complete error message before installing additional packages.

**Frontend cannot connect to the backend**

- Confirm that the backend is running on port `8000`.
- Check the frontend API URL configuration.
- Inspect the browser console and backend terminal for errors.

**Email confirmation or security alerts do not arrive**

- Check the spam folder.
- Verify the Supabase email configuration for confirmation and recovery emails.
- Verify the Gmail SMTP configuration for application alerts.
- Check the terminal logs for email errors and service rate limits.

**Typing-rhythm verification fails**

- Follow the requested typing instructions consistently.
- Check that biometric enrollment has been completed.
- Confirm that the captured samples meet the application's minimum requirements.
- Review backend logs and the actual verification response.

**Port already in use**

Stop the existing server or configure an unused port, updating the corresponding frontend API URL if necessary.

## 10. Security Notes

- Do not expose Supabase service-role keys or SMTP app passwords in frontend code.
- Keep Row-Level Security enabled and verify policies for protected database records and storage objects.
- Protect file access and other sensitive endpoints with the required authorization checks.
- Keep authentication and biometric verification enabled outside any explicitly isolated test environment.
- Do not treat a displayed biometric accuracy percentage as proof of identity or a validated probability of authenticity.
- Test authentication, authorization, lockout, enrollment, and storage access before deploying the system.

## 11. Testing

Run backend tests from the backend directory using the project's configured Python environment:

```powershell
py -m pytest
```

Start the backend from `backend` and the frontend from `frontend` in separate
terminals:

```powershell
python -m uvicorn app.main:app --reload
```

```powershell
npm run dev
```

Run the frontend production build from the frontend directory:

```powershell
npm run build
```

A successful build or passing test suite alone does not establish production security. Verify the complete authentication flow and protected-resource access separately.

## 12. Conclusion

NeuroLock demonstrates the integration of password authentication, behavioral biometric analysis, security notifications, and protected application resources. The project provides a foundation for exploring typing-rhythm authentication and multi-factor security. Further security testing and validation are necessary before production deployment.
