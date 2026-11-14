# 数据库

[English](../en/database.md)

项目沿用上游 v0.2.0 的 SQLite 表结构，SQL 位于 `storage/db.py` 的 `_create_tables`。比赛行保存地面与空中地图哈希、初始占领点摘要、核弹标记及空中坐标换算参数。网页通过哈希取得地图 ID、名称和战斗类型。

## 规范化存储

每个 tick 保存比赛 ID、整数毫秒时间戳、载具与兵种 ID，以及空中视角标记。位置行引用所属 tick，保存对象坐标、颜色、类型、图标和 POI 标记。坐标保留五位小数，换算后的地面坐标可为空。

枚举表集中保存位置与 tick 中重复的字符串。每个连接缓存自己的枚举 ID，事务提交后才把新 ID 加入缓存。接口只需发送一次 tick 元数据，位置通过 `tick_id` 引用它。

```mermaid
erDiagram
    matches ||--o{ ticks : records
    ticks ||--o{ positions : contains
```

## 读取与清理

`GET /api/match/<id>/positions` 返回 `ticks` 和 `positions`。整数 `since` 按毫秒解释，小数按秒解释，结果包含起点时间戳。回放器关联两份列表，存在换算结果时使用地面坐标。

数据库采用 WAL，采集线程和网页请求各自打开连接。删除已结束比赛时，在同一事务中删除位置、tick 和比赛行，再请求增量回收。已有数据库沿用原 SQLite 自动回收模式。采集启动时结束上次中断遗留的比赛。
