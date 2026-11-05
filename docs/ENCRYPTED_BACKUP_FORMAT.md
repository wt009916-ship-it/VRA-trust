# 加密备份封装 v2

backend/encrypted_backup.py调用PyCA cryptography 50.0.2的标准原语，不自行实现AES或scrypt。每个包采用独立16字节随机salt及12字节随机nonce；32字节密钥由scrypt N=131072/r=8/p=1导出，固定版本参数避免从不可信头部选择任意KDF成本。口令16–1024字节且不含NUL/换行，CLI终端采用UTF-8编码；长度下限不能替代高熵口令。

|偏移|长度|内容|
|---:|---:|---|
|0|8|ASCII VRAENC02|
|8|16|salt|
|24|12|nonce|
|36|8|大端无符号内层ZIP字节数|
|44|声明长度|AES-256-GCM密文|
|末尾|16|完整认证标签|

44字节头部作为AAD。按1 MiB分块update，最后finalize；禁止在认证完成前读取解密后的ZIP/SQLite。先比对单独记录的密文SHA-256，再验证长度/版本，认证后再次比对同一打开文件的摘要。加密不隐藏包大小；SHA用于外部记录核对，不是作者签名。

内层沿用已验证的vra-cold-backup-1。恢复记录同时保留内层内容摘要与encrypted_archive_sha256；会话撤销、任务失败修订及历史失效规则不变。临时明文在私有目录；新恢复目录的DACL/mode设置和回读先于数据写入，恢复记录在发布前完成。

独立测试使用CPython hashlib.scrypt导出同参数密钥、PyCA AESGCM单次API双向互操作，核对分块边界和AAD/nonce/tag位置；这验证封装，不是独立密码学认证。实际加密参考恢复脚本采用随机内存口令、不保存，因此复现方式是重新运行脚本生成新包，不承诺可解密旧验收包。普通使用者必须自行保存自己的口令。

固定新增依赖：cryptography50.0.2、cffi2.1.1、pycparser3.12。56个当前Python包的OSV查询零命中只代表查询时刻；不覆盖操作系统或所有捆绑原生库。分发安装包时仍须保留相应许可证，不能把依赖列表当成许可证审计。

依据：[PyCA流式加密与GCM接口](https://cryptography.io/en/latest/hazmat/primitives/symmetric-encryption/)、[PyCA密钥派生](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/)、[Windows创建目录时设置安全描述符](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectoryw)。没有FIPS或第三方密码认证声明。
