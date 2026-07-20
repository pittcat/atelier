# 2. modemcli测试命令

modemcli是运行在C0核，方便调试LTE功能的工具。nxshell

## 2.1 启动RNDIS流程

```bash
modemcli
debug_bes_rpc  7 23 1    // enable modem
debug_bes_rpc  1 1       // enable data
debug_bes_rpc  7 1 2     // 打开rndis
```

## 2.2 拨号流程

```bash
modemcli
debug_bes_rpc  7 23 1       // 开机
debug_bes_rpc  0 14 10086   // 10086通话号码
debug_bes_rpc  0 6          // 挂断
```

## 2.3 Client Ping测试命令流程

```bash
modemcli
debug_bes_rpc  7 23 1
debug_bes_rpc  1 1
!ifconfig                      # 查看网卡
!ping www.baidu.com
!ping6 ipv6-test.com
!ping6 2001:41d0:701:1100::29c8
```

## 2.4 RPC命令分组介绍

### Call

```bash
debug_bes_rpc  0 1           // get ecc list，C0核没打印
debug_bes_rpc  0 2           // get call state
debug_bes_rpc  0 5           // 挂断当前电话
debug_bes_rpc  0 6           // 挂断所有电话
debug_bes_rpc  0 7           // unhold，恢复当前电话
debug_bes_rpc  0 8           // 两通通话，一通在通话中，一通在挂起中，交换两通通话的状态
debug_bes_rpc  0 9           // 保持通话并接听当前通话
debug_bes_rpc  0 10          // 用于释放当前通话并接听来电
debug_bes_rpc  0 11          // 接听来电
debug_bes_rpc  0 12 x        // 发送单个DTMF字符'x'：可以是数字0-9，或者'#'、'*'
```

~~`debug_bes_rpc 0 13`：控制发送停止DTMF时调用此接口。~~

```bash
debug_bes_rpc  0 14 10086    // 10086: call number
```

### Data

```bash
debug_bes_rpc  1 0           // is data active?
debug_bes_rpc  1 1           // data active
debug_bes_rpc  1 2           // data deactive
```

### Radio

```bash
debug_bes_rpc  2 0                         // get rssi
debug_bes_rpc  2 1                         // get current_network_type. 0 2G;1 3G;2 4G;3 5G
debug_bes_rpc  2 2                         // get gprs state
debug_bes_rpc  2 3                         // get ims state
debug_bes_rpc  2 4                         // get volte state
debug_bes_rpc  2 5 1                       // set volte 0/1
debug_bes_rpc  2 6                         // get current_plmn_info
debug_bes_rpc  2 7                         // get fly_mode_state
debug_bes_rpc  2 8 1                       // set fly mode，0:关闭，1:打开
debug_bes_rpc  2 9                         // get current_cell_info
debug_bes_rpc  2 10                        // get lte_cell_info
debug_bes_rpc  2 11                        // get current_plmn_state
debug_bes_rpc  2 12 0                      // 设置搜网模式，0:手动，1:自动
debug_bes_rpc  2 13 mcc mnc mnc_digit_num  // 设置手动搜网网络类型
debug_bes_rpc  2 14                        // get lte_snr
debug_bes_rpc  2 16                        // get current_network_volte_state
debug_bes_rpc  2 17                        // get imei
debug_bes_rpc  2 18 imei                   // set imei
#debug_bes_rpc 2 20                        // set apn
```

### SIM

```bash
debug_bes_rpc  3 0           // get sim_status
debug_bes_rpc  3 1           // get imsi
debug_bes_rpc  3 2           // get iccid
debug_bes_rpc  3 3           // get sim hplmn
```

### SMS

```bash
debug_bes_rpc  4 1 XXX YYYY
```

说明：

- `XXX`：接收短信的号码。
- `YYYY`：自定义短信内容。
- 不指定内容时，发送固定短信：`你好，世界！Hello world!☺，测试编号：`
- 指定内容时，发送 `YYYY` 中的内容。

### SS

```text
callforward_type:
  1：无条件呼叫转移
  3：遇忙呼叫转移
  4：无应答呼叫转移
  5：无法到达移动用户上的呼叫转移

operation_type:
  呼叫转移：开启 0，关闭 1
  呼叫等待：激活 2，去激活 3

num:
  电话号码

no_reply_time:
  无应答时间，仅在设置无应答呼叫转移时使用
```

```bash
debug_bes_rpc  5 0 callforward_type operation_type num no_reply_time  // 设置呼叫转移
debug_bes_rpc  5 1 callforward_type                                   // 获取呼叫转移
debug_bes_rpc  5 2 operation_type                                     // 设置呼叫等待
debug_bes_rpc  5 3                                                    // 获取呼叫等待
debug_bes_rpc  5 4                                                    // 关闭所有呼叫转移
```

### Misc

```bash
debug_bes_rpc  7 6 0    // txdc calib
```

#### USB Control Switch

```bash
debug_bes_rpc  7 1 2    // 打开rndis（RNDIS+CDC0+CDC1）
debug_bes_rpc  7 1 1    // 关闭rndis（RNDIS+CDC0+CDC1）
debug_bes_rpc  7 1 3    // CDC2用于AT（CDC0+CDC1+CDC2），电话功能禁用，用于校准、MDM PCT
debug_bes_rpc  7 1 4    // CDC2用于AT_UI（CDC0+CDC1+CDC2），电话功能启用，用于GCF、CTA
```

#### Engineer Mode

```bash
debug_bes_rpc  7 2 0    // get lte serving cell info
debug_bes_rpc  7 3 0    // get lte neighbour cell info
debug_bes_rpc  7 7 0    // 获取apc1和modem版本信息
debug_bes_rpc  7 9 0    // get lte phy info

debug_bes_rpc  7 12 0   // cell lock（cell_list = {{100, 1},{1300, 5},{400, 7}}）
debug_bes_rpc  7 15 0   // cell unlock（cell_list = {{100, 1},{1300, 5},{400, 7}}）
debug_bes_rpc  7 21 0   // cell unlock all
debug_bes_rpc  7 18 0   // query locked cell

debug_bes_rpc  7 10 0   // band lock（list = {1,3,8}）
debug_bes_rpc  7 13 0   // band unlock（list = {1,3,8}）
debug_bes_rpc  7 10 0   // band lock all
debug_bes_rpc  7 16 0   // query locked bands

debug_bes_rpc  7 11 0   // earfcn lock（list = {100,1300,400}）
debug_bes_rpc  7 14 0   // earfcn unlock（list = {100,1300,400}）
debug_bes_rpc  7 20 0   // earfcn unlock all
debug_bes_rpc  7 13 0   // query locked earfcns

debug_bes_rpc  7 22 0   // get lte cali info
```

#### Non-signaling

```bash
debug_bes_rpc  7 24 30 P1        // 进入非信令（P1: enter or exit）
debug_bes_rpc  7 24 31 P1 P2 P3  // 打开TX（P1: ul_earfcn，P2: power(0~68)，P3: bandwidth(0~5)）
debug_bes_rpc  7 24 32            // 关闭TX
debug_bes_rpc  7 25 33            // 获取TX子帧数和发射状态
debug_bes_rpc  7 24 34 P1 P2      // 打开RX（P1: dl_earfcn，P2: TDD/FDD）
debug_bes_rpc  7 24 35            // 关闭RX
debug_bes_rpc  7 25 36            // 获取RX的RSSI和BLER
```

## 2.5 常用测试流程汇总

### Tele Open

```bash
# 开机第一条
debug_bes_rpc  7 23 1
```

### RNDIS打开流程

```bash
modemcli
debug_bes_rpc  7 23 1    // enable modem
debug_bes_rpc  1 1       // enable data
debug_bes_rpc  7 1 2     // 打开rndis
```

### 通话流程

```bash
modemcli
debug_bes_rpc  7 23 1       // 开机
debug_bes_rpc  0 14 10086   // 10086通话号码
debug_bes_rpc  0 6          // 挂断
```

### C0 Ping测试命令流程

```bash
modemcli
debug_bes_rpc  7 23 1
debug_bes_rpc  1 1
!ifconfig                      # 查看网卡
!ping www.baidu.com
!ping6 ipv6-test.com
!ping6 2001:41d0:701:1100::29c8
```
