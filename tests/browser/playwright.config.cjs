const {defineConfig}=require('playwright/test');
module.exports=defineConfig({
  testDir:__dirname, testMatch:'**/*.spec.cjs', fullyParallel:true,
  timeout:20000, expect:{timeout:8000}, retries:0, workers:2,
  outputDir:'../../.test_artifacts/browser/results',
  reporter:[['list'],['html',{outputFolder:'../../.test_artifacts/browser/report',open:'never'}],['junit',{outputFile:'../../.test_artifacts/browser/junit.xml'}],['./performance-reporter.cjs']],
  use:{baseURL:'http://127.0.0.1:9089',browserName:'chromium',channel:process.env.GNET_BROWSER_CHANNEL||'msedge',headless:true,
    viewport:{width:1440,height:1000},timezoneId:'America/New_York',locale:'en-US',
    trace:'retain-on-failure',screenshot:'only-on-failure'},
  webServer:{command:`"${process.execPath}" server.cjs`,url:'http://127.0.0.1:9089/health',reuseExistingServer:false,timeout:10000},
});
