type WebpackContext = {
  keys(): string[];
  (modulePath: string): unknown;
};

declare const require: {
  context(directory: string, includeSubdirectories: boolean, pattern: RegExp): WebpackContext;
};

describe('frontend coverage inventory', () => {
  it('loads every production application module into the coverage bundle', () => {
    const applicationModules = require.context('./app', true, /^(?!.*\.spec\.ts$).*\.ts$/);
    const modulePaths = applicationModules.keys();

    expect(modulePaths.length).toBeGreaterThan(0);
    modulePaths.forEach((modulePath) => applicationModules(modulePath));
  });
});
