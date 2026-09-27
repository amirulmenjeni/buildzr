export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Dependabot bodies contain long unwrapped markdown links.
    'body-max-line-length': [0],
  },
};
