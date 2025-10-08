# Documentation Setup Guide

This guide will help you set up and publish the MkDocs documentation to GitHub Pages.

## ✅ What's Been Set Up

Your project now has a complete MkDocs documentation system:

- **Configuration**: [mkdocs.yml](mkdocs.yml) - MkDocs configuration with Material theme
- **Documentation**: [docs/](docs/) - Complete documentation structure
- **GitHub Actions**: [.github/workflows/docs.yml](.github/workflows/docs.yml) - Automated deployment
- **Dependencies**: Added to [pyproject.toml](pyproject.toml) under `[project.optional-dependencies.docs]`

## 📦 Installation

Install the documentation dependencies:

```bash
pip install -e ".[docs]"
```

## 🚀 Local Development

### Serve Documentation Locally

Start a local development server with live reload:

```bash
mkdocs serve
```

Then visit: http://127.0.0.1:8000

The documentation will automatically reload when you make changes.

### Build Documentation

Build the static site to the `site/` directory:

```bash
mkdocs build
```

For strict builds (fails on warnings):

```bash
mkdocs build --strict
```

## 📚 Documentation Structure

```
docs/
├── index.md                    # Home page
├── getting-started/
│   ├── installation.md        # Installation guide
│   └── quick-start.md         # Quick start tutorial
├── user-guide/
│   ├── core-concepts.md       # Core concepts
│   ├── workspace.md           # Workspace guide
│   ├── models.md              # Model elements
│   ├── relationships.md       # Relationships
│   ├── views.md               # Views
│   └── styling.md             # Styling
├── examples/
│   ├── system-context.md      # System context example
│   ├── container-view.md      # Container view example
│   └── deployment.md          # Deployment example
├── api/
│   ├── dsl.md                 # DSL API reference
│   └── models.md              # Models API reference
├── contributing.md            # Contributing guide (includes CONTRIBUTING.md)
└── roadmap.md                 # Feature roadmap (includes ROADMAP.md)
```

## 🌐 Publishing to GitHub Pages

### Step 1: Enable GitHub Pages

1. Go to your repository on GitHub: https://github.com/amirulmenjeni/buildzr
2. Click on **Settings** (top navigation)
3. Scroll down to **Pages** (left sidebar under "Code and automation")
4. Under **Source**, select **GitHub Actions** (not "Deploy from a branch")

### Step 2: Push Your Changes

```bash
git add .
git commit -m "Add MkDocs documentation"
git push origin master
```

### Step 3: Monitor Deployment

1. Go to the **Actions** tab in your repository
2. You should see a "Deploy Documentation" workflow running
3. Once it completes (green checkmark), your docs will be live at:

   **https://amirulmenjeni.github.io/buildzr**

### Troubleshooting

If the workflow fails:

1. Check the workflow logs in the Actions tab
2. Ensure GitHub Pages is enabled in repository settings
3. Make sure the repository is public or you have GitHub Pages enabled for private repos
4. Verify the workflow has proper permissions (should be configured automatically)

## 🔄 Automatic Updates

Every time you push to the `master` branch, the documentation will automatically:

1. ✅ Build using the latest content
2. ✅ Run in strict mode (catches broken links)
3. ✅ Deploy to GitHub Pages

## ✏️ Editing Documentation

### Adding New Pages

1. Create a new `.md` file in the appropriate directory under `docs/`
2. Add it to the navigation in `mkdocs.yml`:

```yaml
nav:
  - Home: index.md
  - User Guide:
    - Your New Page: user-guide/your-new-page.md
```

### Using Markdown Features

The documentation supports:

**Admonitions:**
```markdown
!!! note
    This is a note

!!! warning
    This is a warning

!!! tip
    This is a tip
```

**Code blocks with highlighting:**
````markdown
```python
from buildzr.dsl import Workspace

with Workspace('example') as w:
    pass
```
````

**Tabbed content:**
```markdown
=== "Tab 1"
    Content for tab 1

=== "Tab 2"
    Content for tab 2
```

**Include files:**
```markdown
--8<-- "CONTRIBUTING.md"
```

### Linking Between Pages

Use relative links:
```markdown
- [Installation](../getting-started/installation.md)
- [API Reference](../api/dsl.md)
```

## 🎨 Customization

### Change Theme Colors

Edit `mkdocs.yml`:

```yaml
theme:
  palette:
    primary: indigo  # Change to: blue, red, green, etc.
    accent: indigo
```

### Add More Navigation Items

Edit the `nav:` section in `mkdocs.yml`:

```yaml
nav:
  - Home: index.md
  - Your Section:
    - Page 1: section/page1.md
    - Page 2: section/page2.md
```

## 📖 Resources

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [PyMdown Extensions](https://facelessuser.github.io/pymdown-extensions/)
- [Markdown Guide](https://www.markdownguide.org/)

## 🐛 Common Issues

### Issue: Module not found when building

**Solution:** Make sure you've installed the docs dependencies:
```bash
pip install -e ".[docs]"
```

### Issue: GitHub Actions workflow fails

**Solution:** Check that:
1. GitHub Pages is enabled with "GitHub Actions" as source
2. The repository has proper permissions
3. The workflow file is on the `master` branch

### Issue: Changes not showing on GitHub Pages

**Solution:**
1. Wait a few minutes for deployment to complete
2. Clear your browser cache (Ctrl+F5 or Cmd+Shift+R)
3. Check the Actions tab to ensure deployment succeeded

## 🎉 Next Steps

1. ✅ Install dependencies: `pip install -e ".[docs]"`
2. ✅ Test locally: `mkdocs serve`
3. ✅ Enable GitHub Pages in repository settings
4. ✅ Push to `master` branch
5. ✅ Visit your live docs at https://amirulmenjeni.github.io/buildzr

Your documentation is ready to go! 🚀
