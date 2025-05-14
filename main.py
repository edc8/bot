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

    @filter.command("记录收入")
    async def add_income(self, event: AstrMessageEvent):
        """记录一笔收入"""
        user_id = event.get_sender_id()
        parts = event.message_str.strip().split()
        if len(parts) < 3:
            yield event.plain_result("格式错误，请使用: /记录收入 [金额] [类别] [备注]")
            return

        try:
            amount = float(parts[1])
            if amount <= 0:
                raise ValueError("金额必须大于0")
        except ValueError:
            yield event.plain_result("金额格式错误，请输入有效的数字")
            return

        category = parts[2]
        if category not in self.categories["收入"]:
            yield event.plain_result(f"收入类别错误，可用类别: {', '.join(self.categories['收入'])}")
            return

        note = " ".join(parts[3:]) if len(parts) > 3 else ""

        # 创建收入记录
        record = {
            "id": len(self.records.get(user_id, [])) + 1,
            "type": "收入",
            "amount": amount,
            "category": category,
            "note": note,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 添加到用户记录
        if user_id not in self.records:
            self.records[user_id] = []
        self.records[user_id].append(record)
        self._save_data()

        yield event.plain_result(f"成功记录 {amount} 元收入 ({category})")

    @filter.command("记录支出")
    async def add_expense(self, event: AstrMessageEvent):
        """记录一笔支出"""
        user_id = event.get_sender_id()
        parts = event.message_str.strip().split()
        if len(parts) < 3:
            yield event.plain_result("格式错误，请使用: /记录支出 [金额] [类别] [备注]")
            return

        try:
            amount = float(parts[1])
            if amount <= 0:
                raise ValueError("金额必须大于0")
        except ValueError:
            yield event.plain_result("金额格式错误，请输入有效的数字")
            return

        category = parts[2]
        if category not in self.categories["支出"]:
            yield event.plain_result(f"支出类别错误，可用类别: {', '.join(self.categories['支出'])}")
            return

        note = " ".join(parts[3:]) if len(parts) > 3 else ""

        # 创建支出记录
        record = {
            "id": len(self.records.get(user_id, [])) + 1,
            "type": "支出",
            "amount": amount,
            "category": category,
            "note": note,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 添加到用户记录
        if user_id not in self.records:
            self.records[user_id] = []
        self.records[user_id].append(record)
        self._save_data()

        yield event.plain_result(f"成功记录 {amount} 元支出 ({category})")

    @filter.command("查询账单")
    async def query_records(self, event: AstrMessageEvent):
        """查询最近的账单记录"""
        user_id = event.get_sender_id()
        if user_id not in self.records or not self.records[user_id]:
            yield event.plain_result("您还没有任何记账记录")
            return

        parts = event.message_str.strip().split()
        days = 7  # 默认查询7天内的记录
        if len(parts) > 1:
            try:
                days = int(parts[1])
                if days <= 0:
                    days = 7
            except ValueError:
                pass

        # 获取当前时间和指定天数前的时间
        now = datetime.now()
        records = []

        # 筛选符合条件的记录
        for record in reversed(self.records[user_id]):
            record_time = datetime.strptime(record["timestamp"], "%Y-%m-%d %H:%M:%S")
            delta = now - record_time
            if delta.days <= days:
                records.append(record)
            else:
                break  # 按时间倒序排列，后面的记录时间更早，无需继续检查

        if not records:
            yield event.plain_result(f"您在最近 {days} 天内没有任何记账记录")
            return

        # 构建结果文本
        result = f"最近 {days} 天的账单记录:\n"
        for i, record in enumerate(records, 1):
            result += f"{i}. {record['timestamp']} | {record['type']} {record['amount']}元 | {record['category']}"
            if record["note"]:
                result += f" | {record['note']}"
            result += "\n"

        yield event.plain_result(result)

    @filter.command("账单统计")
    async def statistics(self, event: AstrMessageEvent):
        """统计收支情况"""
        user_id = event.get_sender_id()
        if user_id not in self.records or not self.records[user_id]:
            yield event.plain_result("您还没有任何记账记录")
            return

        parts = event.message_str.strip().split()
        days = 30  # 默认统计30天内的数据
        if len(parts) > 1:
            try:
                days = int(parts[1])
                if days <= 0:
                    days = 30
            except ValueError:
                pass

        # 获取当前时间和指定天数前的时间
        now = datetime.now()
        income_total = 0
        expense_total = 0
        income_categories = {cat: 0 for cat in self.categories["收入"]}
        expense_categories = {cat: 0 for cat in self.categories["支出"]}

        # 统计符合条件的记录
        for record in self.records[user_id]:
            record_time = datetime.strptime(record["timestamp"], "%Y-%m-%d %H:%M:%S")
            delta = now - record_time
            if delta.days > days:
                continue

            if record["type"] == "收入":
                income_total += record["amount"]
                income_categories[record["category"]] += record["amount"]
            else:
                expense_total += record["amount"]
                expense_categories[record["category"]] += record["amount"]

        # 构建结果文本
        result = f"最近 {days} 天的收支统计:\n"
        result += f"总收入: {income_total} 元\n"
        result += "收入分类:\n"
        for cat, amount in income_categories.items():
            if amount > 0:
                result += f"  {cat}: {amount} 元\n"

        result += f"\n总支出: {expense_total} 元\n"
        result += "支出分类:\n"
        for cat, amount in expense_categories.items():
            if amount > 0:
                result += f"  {cat}: {amount} 元\n"

        result += f"\n结余: {income_total - expense_total} 元"
        yield event.plain_result(result)

    @filter.command("删除记录")
    async def delete_record(self, event: AstrMessageEvent):
        """删除指定记录"""
        user_id = event.get_sender_id()
        if user_id not in self.records or not self.records[user_id]:
            yield event.plain_result("您还没有任何记账记录")
            return

        parts = event.message_str.strip().split()
        if len(parts) < 2:
            yield event.plain_result("请指定要删除的记录序号")
            return

        try:
            index = int(parts[1]) - 1  # 用户输入的序号从1开始
            if 0 <= index < len(self.records[user_id]):
                deleted = self.records[user_id].pop(index)
                # 更新后续记录的id
                for i, record in enumerate(self.records[user_id], start=index):
                    record["id"] = i + 1
                self._save_data()
                yield event.plain_result(f"已删除记录: {deleted['type']} {deleted['amount']}元 ({deleted['category']})")
            else:
                yield event.plain_result("无效的记录序号")
        except ValueError:
            yield event.plain_result("请输入有效的序号")

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
            # 从消息中提取JSON数据（跳过命令部分）
            json_str = event.message_str.strip()[5:].strip()
            if not json_str:
                raise ValueError("请提供JSON数据")
                
            data = json.loads(json_str)
            if not isinstance(data, list):
                raise ValueError("数据格式不正确，应为JSON数组")
            
            # 验证每条记录的格式
            for record in data:
                if not isinstance(record, dict):
                    raise ValueError("记录格式不正确")
                required_fields = ["type", "amount", "category", "timestamp"]
                for field in required_fields:
                    if field not in record:
                        raise ValueError(f"记录缺少必要字段: {field}")
                if record["type"] not in ["收入", "支出"]:
                    raise ValueError("无效的记录类型")
                if (record["type"] == "收入" and record["category"] not in self.categories["收入"]) or \
                   (record["type"] == "支出" and record["category"] not in self.categories["支出"]):
                    raise ValueError(f"无效的类别: {record['category']}")
            
            if user_id not in self.records:
                self.records[user_id] = []
            
            # 合并记录并重新分配ID
            existing_ids = {record["id"] for record in self.records[user_id]}
            max_id = max(existing_ids) if existing_ids else 0
            
            for record in data:
                # 避免ID冲突
                while record["id"] in existing_ids:
                    max_id += 1
                    record["id"] = max_id
                existing_ids.add(record["id"])
                self.records[user_id].append(record)
            
            # 按时间戳排序
            self.records[user_id].sort(key=lambda x: x["timestamp"])
            
            self._save_data()
            yield event.plain_result(f"成功导入 {len(data)} 条记录")
        except json.JSONDecodeError:
            yield event.plain_result("JSON格式解析失败，请检查数据格式")
        except ValueError as ve:
            yield event.plain_result(f"导入失败: {str(ve)}")
        except Exception as e:
            logger.error(f"导入数据失败: {str(e)}")
            yield event.plain_result(f"导入失败: 未知错误")

    async def terminate(self):
        """插件卸载时保存数据"""
        self._save_data()
        logger.info("本地记账插件已卸载")
