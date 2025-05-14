from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from datetime import datetime
from typing import Dict, List
import json
import os

@register("accounting", "YourName", "纯本地记账插件", "1.0.0", need_llm=False)
class LocalAccountingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_file = os.path.join(os.path.dirname(__file__), "accounting_data.json")
        self.records: Dict[str, List[Dict]] = {}  # 用户ID -> 账单记录列表
        self.categories = {
            "收入": ["工资", "奖金", "投资", "其他收入"],
            "支出": ["餐饮", "购物", "交通", "娱乐", "住房", "医疗", "教育", "其他支出"]
        }

    async def initialize(self):
        """加载本地数据文件"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self.records = json.load(f)
            logger.info("本地记账插件初始化完成，数据已加载")
        except Exception as e:
            logger.error(f"加载数据文件失败: {str(e)}")
            self.records = {}

    def _save_data(self):
        """保存数据到本地文件"""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据文件失败: {str(e)}")

    @filter.command("记账帮助")
    async def accounting_help(self, event: AstrMessageEvent):
        """显示本地记账帮助信息"""
        help_text = """本地记账插件使用说明(无需联网):
/记录收入 [金额] [类别] [备注] - 记录收入
/记录支出 [金额] [类别] [备注] - 记录支出
/查询账单 [天数] - 查询最近账单
/账单统计 [天数] - 统计收支情况
/删除记录 [序号] - 删除指定记录
/导出账单 - 导出全部账单数据(JSON格式)
/导入账单 [JSON数据] - 导入账单数据

可用类别:
收入: """ + "、".join(self.categories["收入"]) + """
支出: """ + "、".join(self.categories["支出"])
        yield event.plain_result(help_text)

    # [...] 保持之前的 add_income, add_expense, query_records 等方法不变
    # 只需确保所有操作都使用 self.records 和 self._save_data()

    @filter.command("导出账单")
    async def export_records(self, event: AstrMessageEvent):
        """导出用户的全部账单数据"""
        user_id = event.get_sender_id()
        if user_id not in self.records or not self.records[user_id]:
            yield event.plain_result("您还没有任何记账记录")
            return
        
        try:
            user_data = json.dumps(self.records[user_id], ensure_ascii=False, indent=2)
            yield event.plain_result(f"您的账单数据(可用于备份或导入):\n{user_data}")
        except Exception as e:
            logger.error(f"导出数据失败: {str(e)}")
            yield event.plain_result("导出数据失败")

    @filter.command("导入账单")
    async def import_records(self, event: AstrMessageEvent):
        """导入账单数据"""
        user_id = event.get_sender_id()
        try:
            data = json.loads(event.message_str)
            if not isinstance(data, list):
                raise ValueError("数据格式不正确")
            
            if user_id not in self.records:
                self.records[user_id] = []
            
            self.records[user_id].extend(data)
            self._save_data()
            yield event.plain_result(f"成功导入 {len(data)} 条记录")
        except json.JSONDecodeError:
            yield event.plain_result("JSON格式解析失败，请检查数据格式")
        except Exception as e:
            yield event.plain_result(f"导入失败: {str(e)}")

    async def terminate(self):
        """插件卸载时保存数据"""
        self._save_data()
        logger.info("本地记账插件已卸载")
