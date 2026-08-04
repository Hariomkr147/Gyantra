# Deploying Gyantra for Free

Gyantra is designed as a decoupled full-stack application: a **React frontend** and a **Python FastAPI backend**.

To host this for free, we recommend splitting the deployment across two free-tier friendly platforms:
1. **Frontend**: [Netlify](https://www.netlify.com/) (Fast, free global CDN for static React apps)
2. **Backend**: [Render.com](https://render.com/) (Great free tier for Python web services)

---

## Step 1: Push your code to GitHub

Both Netlify and Render deploy directly from GitHub.

1. Create a free GitHub account if you don't have one.
2. Initialize Git in your project folder, commit all files, and push them to a **Public** (or private) GitHub repository named `gyantra`.
3. *(Ensure your `.env` file with actual API keys is never committed. Only `.env.example` should be in the repo, which has been scrubbed for you).*

---

## Step 2: Deploy the Backend (Render)

1. Sign up for [Render.com](https://render.com/) using your GitHub account.
2. Go to your Dashboard and click **New** -> **Web Service**.
3. Select **"Build and deploy from a Git repository"**.
4. Connect your GitHub account and select your `gyantra` repository.
5. Fill out the settings as follows:
   - **Name**: `gyantra-api` (or any unique name)
   - **Branch**: `main`
   - **Root Directory**: `backend` (Important: type exactly `backend`)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`
6. Click **Advanced** -> **Add Environment Variable** and add:
   - `DEMO_MODE` = `true` (Or provide your real API keys like `GEMINI_API_KEY`)
   - `DOCLING_ENABLED` = `false`
7. Click **Create Web Service**.

> **Wait for it to build.** Once it finishes, Render will give you a URL like `https://gyantra-api.onrender.com`. Keep this URL handy.

---

## Step 3: Deploy the Frontend (Netlify)

1. Sign up for [Netlify](https://www.netlify.com/) using your GitHub account.
2. Click **Add new site** -> **Import an existing project**.
3. Select **GitHub** and authorize Netlify.
4. Pick your `gyantra` repository.
5. Fill out the settings:
   - **Base directory**: `frontend`
   - **Build command**: `npm run build`
   - **Publish directory**: `frontend/dist`
6. Click **Show advanced** -> **New Variable** and add:
   - Key: `VITE_API_URL`
   - Value: The URL from your Render backend (e.g. `https://gyantra-api.onrender.com/api`)
7. Click **Deploy site**.

Netlify will build your React app and assign it a URL (like `https://some-name.netlify.app`). 

---

## Step 4: Configure CORS (Connecting them)

For security, the Render backend needs to know it's allowed to accept requests from the Netlify frontend.

1. Go back to your Render Dashboard -> **gyantra-api** -> **Environment**.
2. Add a new variable:
   - Key: `CORS_ORIGINS`
   - Value: Your Netlify URL (e.g., `https://some-name.netlify.app`)
3. Click **Save Changes**. Render will automatically restart your backend.

---

## Step 5: Test the Deployment

1. Visit your Netlify URL.
2. The UI should load. Try uploading a sample document.
3. Because the backend is on Render's free tier, **it spins down after 15 minutes of inactivity**. The very first upload after a period of inactivity might take ~50 seconds to respond as the backend wakes up. Subsequent requests will be fast!

> **Note on Docling:** To stay within the memory limits of the free tier, the heavyweight `docling` parser has been disabled for deployment. Gyantra will automatically fall back to its fast, built-in parsers (PyMuPDF).
