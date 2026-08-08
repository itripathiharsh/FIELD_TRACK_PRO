/* ESLint configuration for the FieldTrack Pro admin dashboard.
 *
 * Scope note: this config is intentionally conservative. It is here to catch
 * real defects (unused code, unsafe `any`, broken hook dependencies) during the
 * repair program - not to trigger a stylistic rewrite of an approved codebase.
 */
module.exports = {
  root: true,
  env: { browser: true, es2020: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'coverage', 'node_modules', '.eslintrc.cjs', '*.config.js'],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  plugins: ['@typescript-eslint', 'react-refresh'],
  settings: { react: { version: '18.3' } },
  rules: {
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

    // Contract-mismatch guard: `as any` was used to paper over API/type
    // divergence (FT-003). Surface it rather than allow it silently.
    '@typescript-eslint/no-explicit-any': 'warn',

    '@typescript-eslint/no-unused-vars': [
      'error',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
    ],

    // Debug output must not ship; console.warn/error remain allowed.
    'no-console': ['error', { allow: ['warn', 'error'] }],

    eqeqeq: ['error', 'smart'],
    'no-var': 'error',
    'prefer-const': 'error',
  },
  overrides: [
    {
      files: ['**/*.test.ts', '**/*.test.tsx', 'src/test/**'],
      env: { node: true },
      rules: {
        '@typescript-eslint/no-explicit-any': 'off',
        'no-console': 'off',
      },
    },
  ],
};
