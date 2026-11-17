@核心
Feature: 文字标签解析
  Scenario: 空块没有内容
    When 解析文字块 ""
    Then 文字项数量是 0

  Scenario: 行尾 |N 表示份数
    When 解析文字块 "贴纸|3"
    Then 文字项数量是 1
    And 第一项份数是 3
    And 第一项文本是 "贴纸"

  Scenario: 空行被忽略、其余按行展开
    When 解析文字块 "A\n\nB|2\n"
    Then 文字项数量是 2
