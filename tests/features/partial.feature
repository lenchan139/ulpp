@核心
Feature: 接着打的排格
  Scenario: 空格多于内容时全部放进
    Given 空闲格子 "0,1,2"
    And 内容 2 条
    When 计算放格
    Then 放进 2 格
    And 剩余 0 条

  Scenario: 没有空格子时什么都放不下
    Given 空闲格子 ""
    And 内容 1 条
    When 计算放格
    Then 放进 0 格
    And 剩余 1 条

  Scenario Outline: 内容比空格多时截断并报告剩余
    Given 空闲格子 "<free>"
    And 内容 <n> 条
    When 计算放格
    Then 放进 <placed> 格
    And 剩余 <left> 条

    Examples:
      | free | n | placed | left |
      | 0,1  | 4 | 2      | 2    |
      | 7    | 3 | 1      | 2    |
