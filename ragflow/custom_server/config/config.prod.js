module.exports = {
  port: 80,
  appName: "rhis_server",
  appDomainName: "", //应用域名
  authKeyWord: "rhis_server",
  configUrl: "http://127.0.0.1:3001/api/config/baseFrame/dev", //统一配置地址
  clusterWorkerNum: 1, //应用运行的进程数，1：开启单进程模式，0：开启多进程模式，进程数=CPU数量，>1:开启多进程模式，数量为设置数量。多进程模式下，需要Redis的支持，isShareMemory必须为true
  isShareMemory: true, //是否使用共享内存，当是多进程模式时必须为true，单进程模式时，可以为false或true
  isHttps: false,
  isVerificationUrl: false, //是否开启url地址检测防篡改功能
  isUseMqtt: false, //是否使用MQTT通信模块
  isUseTask: false, //是否使用调度任务模块
  staticUrl: "https://licos.obs.cn-south-1.myhuaweicloud.com/licos-web", //静态资源服务器URL
  tenantStaticUrl: "https://licos-tenant.obs.cn-south-1.myhuaweicloud.com/[tenantId]/app-data/portal_site", //租户静态资源地址
  webSiteApiUrl: "",
  isAutoPublishCMSOnStart: false, //是否在重启的时候,自动发布站点
  emrStructuredPath: "D:\\项目\\rhis_data_server\\source\\emr-html", //导出的病历文件路径
  emrTemplatePath: "D:\\项目\\rhis_data_server\\source\\emr-template", //模版路径
  llm: {
    apiKey: "sk-9c92044c17d0478b86e16c69ab3f8dab",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    // baseUrl: "http://127.0.0.1:11434/v1",
  },
  DB: {
    default: {
      host: "mysql",
      port: "3306",
      user: "root",
      pwd: "infini_rag_flow",
      dbName: "rag_flow",
      dialect: "mysql",
      dirName: "data-base",
      logging: false,
    },

  },

  redis: {
    baseKey: "rhis_server:",
    host: "redis",
    port: 6379,
    password: "infini_rag_flow",
    family: 4, // 4 (IPv4) or 6 (IPv6)
    db: 1,
    pool: {
      maxConnections: 20,
    },
  },
  s3Object: {
    curS3: "local",
    obs: {
      //华为 OBS
      type: "obs",
      endPoint: "obs.cn-south-1.myhuaweicloud.com", //这里不能带http或者https
      useSSL: false, //不需要https
      accessKey: "ZAU99DLJPFZG9DKYYALY", //账号密码同web登陆时一致
      secretKey: "CwjmVLbJjpy8OUzN3B9DoB0UQ5B8F8324KwSPYk1",
      bucketName: "licos",
      basePath: "licos-web",
      url: "https://licos.obs.cn-south-1.myhuaweicloud.com/licos-web",
    },
    obs_tenant: {
      //华为 OBS
      type: "obs",
      endPoint: "obs.cn-south-1.myhuaweicloud.com", //这里不能带http或者https
      useSSL: false, //不需要https
      accessKey: "ZAU99DLJPFZG9DKYYALY", //账号密码同web登陆时一致
      secretKey: "CwjmVLbJjpy8OUzN3B9DoB0UQ5B8F8324KwSPYk1",
      bucketName: "licos-tenant",
      basePath: "[tenantId]/app-data/portal_site",
      url: "https://licos-tenant.obs.cn-south-1.myhuaweicloud.com/[tenantId]/app-data/portal_site",
    },
    minio: {
      type: "minio",
      endPoint: "tianling.imdo.co", //这里不能带http或者https
      port: 9000,
      useSSL: false, //不需要https
      accessKey: "public", //账号密码同web登陆时一致
      secretKey: "tianling2000",
      bucketName: "default",
      basePath: "",
      url: "http://tianling.imdo.co:9000/default",
    },
    minio_tenant: {
      type: "minio",
      endPoint: "tianling.imdo.co", //这里不能带http或者https
      port: 9000,
      useSSL: false, //不需要https
      accessKey: "public", //账号密码同web登陆时一致
      secretKey: "tianling2000",
      bucketName: "tenant",
      basePath: "[tenantId]/app-data/portal_site",
      url: "http://tianling.imdo.co:9000/tenant/[tenantId]/app-data/portal_site",
    },
    local: {
      type: "local",
      bucketName: "/www/res",
      basePath: "",
      url: "http://127.0.0.1:30100/res",
    },
    local_tenant: {
      type: "local",
      bucketName: "/www/res",
      basePath: "/upload/[tenantId]",
      url: "http://127.0.0.1:30100/res/upload/[tenantId]",
    },
  },

  log4js: {
    appenders: {
      ruleConsole: {
        type: "console",
        layout: {
          type: "pattern",
          pattern: "[%c] %d{yyyy-MM-dd hh:mm:ss.SSS} %p %m",
        },
      },
      ruleFile: {
        type: "dateFile",
        filename: "./logs/server-",
        pattern: "yyyy-MM-dd.log",
        encoding: "utf-8",
        maxLogSize: 10 * 1000 * 1000,
        numBackups: 3,
        alwaysIncludePattern: true,
        layout: {
          type: "pattern",
          pattern: "[%c] %d{yyyy-MM-dd hh:mm:ss.SSS} %p %m",
        },
      },
    },
    categories: {
      default: {
        appenders: ["ruleConsole", "ruleFile"],
        level: "all", //ALL<TRACE<DEBUG<INFO<WARN<ERROR<FATAL<MARK<OFF
      },
      // file: {
      //     appenders: ['ruleFile'],
      //     level: 'all'
      // }
    },
    replaceConsole: true,
    pm2: true,
  },
  mqtt: {
    webApi: "http://118.24.108.238:32006/api/v2",
    host: "mqtt://118.24.108.238:52727",
    auth: {
      username: "admin",
      password: "public",
    },
  },
  task: {
    host: "http://localhost:80/socket/task/manage",
  }
};

