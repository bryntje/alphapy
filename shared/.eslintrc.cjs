module.exports = {
  root: true,
  extends: [
    "next/core-web-vitals",
    "next/typescript",
    "eslint:recommended",
    "plugin:react-hooks/recommended",
    "prettier",
  ],
  parserOptions: {
    project: true,
  },
  rules: {
    "react-hooks/exhaustive-deps": ["warn"],
  },
};
