COPY THIS FOLDER INTO YOUR REPO AS .github/workflows/
====================================================

GitHub hides folders that start with a dot (.github), so we use this visible
folder name instead.

IN YOUR ADios REPO (on your computer or on GitHub):

1. Create the folder path:   .github/workflows/
   - If you're on GitHub.com: Add file → Create new file →
     type:  .github/workflows/update-hosts.yml
   - If you're on your PC: Create folder ".github", inside it create "workflows".

2. Copy the FILE from this folder into that path:
   - Copy "update-hosts.yml" from here (github-workflows)
   - Put it inside your repo at:  .github/workflows/update-hosts.yml

Result: Your repo must contain the file:
  .github/workflows/update-hosts.yml

Then commit and push. The Actions tab will show "Update hosts".
