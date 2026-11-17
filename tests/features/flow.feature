@核心
Feature: v2 向导状态机
  Background:
    Given 全新的向导

  Scenario: 三站走完即完成
    When 连续前进 2 步
    Then 当前站是 "output"
    When 在最后一站跳过
    Then 向导已完成

  Scenario: 回退不能越过第一站
    When 连续前进 1 步
    When 回退一步
    When 再回退一步
    Then 当前站是 "sheet"

  Scenario Outline: 跳到指定站
    When 跳到 <目标>
    Then 当前站是 <结果>

    Examples:
      | 目标    | 结果   |
      | orient | orient |
      | 2      | output |

  Scenario: 答案存进进度并读取一致
    When 回答 "paper" 为 "45"
    When 保存进度
    When 重新读取进度
    Then 答案 "paper" 是 "45"

  Scenario: 损坏的存档从第一站开始
    When 写入坏存档 "{坏"
    When 重新读取进度
    Then 当前站是 "sheet"
    And 没有记录错误
