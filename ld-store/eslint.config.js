import js from '@eslint/js'
import globals from 'globals'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

const appFiles = ['src/**/*.{js,vue}']
const toolFiles = [
  'eslint.config.js',
  'vite.config.js',
  'vitest.config.js',
  'tests/network-sandbox.js',
  'postcss.config.js',
  'tailwind.config.js',
  'scripts/**/*.js'
]

export default [
  {
    ignores: ['dist/**', '.csp-smoke-dist/**', 'node_modules/**', '.wrangler/**']
  },
  {
    ...js.configs.recommended,
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module'
    }
  },
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.ts'],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module'
      },
      globals: {
        ...globals.browser
      }
    },
    plugins: {
      '@typescript-eslint': tseslint.plugin
    },
    rules: {
      ...tseslint.configs.recommended.rules,
      'no-undef': 'off',
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^(_|error|e)$'
        }
      ]
    }
  },
  {
    files: ['src/**/*.vue', 'tests/**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser
      }
    }
  },
  {
    files: appFiles,
    languageOptions: {
      globals: {
        ...globals.browser
      }
    },
    rules: {
      // 现阶段先确保基础问题可见，但不因历史包袱阻塞迭代
      'no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^(_|error|e)$'
        }
      ],
      '@typescript-eslint/no-unused-vars': 'off',
      'vue/multi-word-component-names': 'off'
    }
  },
  {
    files: toolFiles,
    languageOptions: {
      globals: {
        ...globals.node
      }
    }
  },
  {
    files: ['public/_worker.js', 'tests/worker-open-graph.test.js'],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node
      }
    }
  }
]
