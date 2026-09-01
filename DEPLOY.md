# FPL League Dashboard - Deployment Guide

## Deploy to Streamlit Cloud

### Prerequisites
- GitHub account with the repository pushed
- Streamlit Cloud account (free at https://streamlit.io/cloud)

### Step 1: Push to GitHub

Commit and push all changes to your main branch:

```bash
cd /workspaces/FPL_app
git add -A
git commit -m "Add export to JPEG and email notification features"
git push origin main
```

### Step 2: Deploy on Streamlit Cloud

1. Go to [Streamlit Cloud](https://streamlit.io/cloud)
2. Click **"New app"**
3. Select:
   - **Repository**: ethk0123-collab/FPL_app
   - **Branch**: main
   - **Main file path**: app.py
4. Click **"Deploy"**

### Step 3: Configure Secrets (for Email Feature)

1. In the Streamlit Cloud dashboard, go to your app
2. Click the **three dots (⋮)** → **Settings**
3. Go to **"Secrets"** tab
4. Copy and paste the following:

```toml
[email]
sender = "etethk123@gmail.com"
password = "fk031102"
recipient = "ethk0123@gmail.com"
```

5. Click **"Save"**

### What's Deployed

✅ **Export to JPEG** - Available immediately (generates JPEG or HTML)  
✅ **Email Notifications** - Works with configured secrets  
✅ **League Dashboard** - Full functionality  
✅ **Weekly Overview** - Prison League statistics  

### Features

- 📊 League Overview with manager standings
- 🔍 Squad Inspector for individual managers
- 🎯 Player Selection Heatmap
- 📥 Export Weekly Overview as JPEG/HTML
- 📧 Automatic email when gameweek finishes
- 🎮 Top Players section (password protected)

### Environment Variables

The app uses Streamlit secrets for email credentials on Cloud:
- `[email].sender` - Gmail sender address
- `[email].password` - Gmail app password
- `[email].recipient` - Email recipient address

### Troubleshooting

**App won't load?**
- Check the Logs tab in Streamlit Cloud dashboard
- Verify all dependencies in requirements.txt
- Ensure main branch is up to date on GitHub

**Email not sending?**
- Verify secrets are configured correctly
- Check Gmail app password (not regular password)
- Ensure 2-Factor Authentication is enabled on Gmail

**Export button not working?**
- App generates HTML as fallback if JPEG fails
- Ensure plotly is installed (check requirements.txt)

### Local Development

To test locally before deploying:

```bash
cd /workspaces/FPL_app
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501 in your browser.

### Support

For issues, check:
1. [Streamlit Documentation](https://docs.streamlit.io)
2. [Streamlit Cloud Troubleshooting](https://docs.streamlit.io/streamlit-cloud/troubleshooting)
3. App logs in Streamlit Cloud dashboard
