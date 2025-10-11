from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Dict, List, Optional
import json
import os
import time
import uuid


@register(
    name="accounting",  # 插件唯一标识（必填）
    author="anchor",    # 作者信息（必填）
    description="提供基础记账和AA分账功能，支持收支记录、统计和多人账单管理",  # 功能描述（必填）
    version="1.5.0"     # 版本号（必填）
)
class AccountingPlugin(Star):
    """
    记账插件主类，继承自AstrBot的Star基类
    实现基础记账和AA分账功能
    """
    def __init__(self, context: Context):
        """
        初始化插件
        :param context: 插件上下文对象，由框架传入
        """
        super().__init__(context)
        # 数据存储结构
        self.user_records: Dict[str, List[Dict]] = {}  # {用户ID: [记录列表]}
        self.aa_bills: Dict[str, List[Dict]] = {}      # {用户ID: [AA账单列表]}
        
        # 数据文件路径（遵循AstrBot插件数据存储规范）
        self.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(self.data_dir, exist_ok=True)  # 确保数据目录存在
        self.acc_data_path = os.path.join(self.data_dir, "accounting_records.json")
        self.aa_data_path = os.path.join(self.data_dir, "aa_bills.json")
        
        # 加载历史数据
        self._load_data()
        logger.info(f"记账插件 v{self.version} 初始化完成")

    # ---------------------- 框架要求的生命周期方法 ----------------------
    async def initialize(self):
        """插件初始化方法，框架会自动调用"""
        logger.info("记账插件初始化中...")
        # 可以在这里添加额外的初始化逻辑

    async def terminate(self):
        """插件终止方法，框架会在卸载时调用"""
        self._save_data()
        logger.info(f"记账插件 v{self.version} 已卸载，数据已保存")

    # ---------------------- 命令注册（遵循AstrBot命令规范） ----------------------
    @filter.command_group("ac", aliases=["记账"], description="记账主命令组")
    def accounting_command_group(self):
        """记账功能主命令组"""
        pass

    # ---------------------- 基础记账命令 ----------------------
    @accounting_command_group.command("help", aliases=["帮助"], description="显示帮助信息")
    async def cmd_help(self, event: AstrMessageEvent):
        """显示所有可用命令的帮助信息"""
        help_text = (
            "📊 记账插件帮助（v1.5.0）\n"
            "===============================\n"
            "【基础记账】\n"
            "/ac + [金额] [来源] [备注]   - 添加收入记录\n"
            "  例：/ac + 5000 工资 6月份\n"
            "/ac - [金额] [分类] [备注]   - 添加支出记录\n"
            "  例：/ac - 35 餐饮 晚餐\n"
            "/ac 查 [条数]               - 查看记账记录，默认10条\n"
            "  例：/ac 查 5\n"
            "/ac 汇总                    - 查看收支汇总统计\n"
            "/ac 删 [记录ID]             - 删除指定记录\n"
            "  例：/ac 删 a1b2c3d4\n"
            "\n【AA分账】\n"
            "/ac aa [参与人1] [参与人2] [金额] - 创建AA账单\n"
            "  例：/ac aa 张三 李四 300\n"
            "/ac aa 对账                 - 查看所有AA账单\n"
            "/ac aa 清账 [账单ID]        - 标记AA账单为已清账\n"
            "  例：/ac aa 清账 ab12\n"
            "===============================\n"
            f"插件版本：v{self.version} | 作者：{self.author}"
        )
        yield event.plain_result(help_text)

    @accounting_command_group.command("+", description="添加收入记录")
    async def cmd_add_income(self, event: AstrMessageEvent, amount: str, source: str, note: Optional[str] = ""):
        """
        添加收入记录
        :param amount: 金额
        :param source: 收入来源
        :param note: 备注信息（可选）
        """
        user_id = event.get_sender_id()
        try:
            # 验证金额
            amount_val = float(amount)
            if amount_val <= 0:
                raise ValueError("金额必须大于0")
                
            # 创建记录
            timestamp = int(time.time())
            record = {
                "id": str(uuid.uuid4())[:8],  # 8位短ID
                "type": "income",
                "amount": round(amount_val, 2),
                "source": source,
                "note": note.strip() if note else "",
                "create_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
                "timestamp": timestamp
            }
            
            # 保存记录
            self.user_records.setdefault(user_id, []).append(record)
            self._save_data()
            
            # 返回结果
            yield event.plain_result(
                f"✅ 收入记录添加成功\n"
                f"金额：{record['amount']} 元\n"
                f"来源：{source}\n"
                f"时间：{record['create_time']}\n"
                f"记录ID：{record['id']}"
            )
            
        except ValueError as e:
            yield event.plain_result(f"❌ 收入记录添加失败：{str(e)}")
        except Exception as e:
            logger.error(f"添加收入记录出错：{str(e)}")
            yield event.plain_result(f"❌ 系统错误：{str(e)}")

    @accounting_command_group.command("-", description="添加支出记录")
    async def cmd_add_expense(self, event: AstrMessageEvent, amount: str, category: str, note: Optional[str] = ""):
        """
        添加支出记录
        :param amount: 金额
        :param category: 支出分类
        :param note: 备注信息（可选）
        """
        user_id = event.get_sender_id()
        try:
            # 验证金额
            amount_val = float(amount)
            if amount_val <= 0:
                raise ValueError("金额必须大于0")
                
            # 创建记录
            timestamp = int(time.time())
            record = {
                "id": str(uuid.uuid4())[:8],  # 8位短ID
                "type": "expense",
                "amount": round(amount_val, 2),
                "category": category,
                "note": note.strip() if note else "",
                "create_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
                "timestamp": timestamp
            }
            
            # 保存记录
            self.user_records.setdefault(user_id, []).append(record)
            self._save_data()
            
            # 返回结果
            yield event.plain_result(
                f"✅ 支出记录添加成功\n"
                f"金额：{record['amount']} 元\n"
                f"分类：{category}\n"
                f"时间：{record['create_time']}\n"
                f"记录ID：{record['id']}"
            )
            
        except ValueError as e:
            yield event.plain_result(f"❌ 支出记录添加失败：{str(e)}")
        except Exception as e:
            logger.error(f"添加支出记录出错：{str(e)}")
            yield event.plain_result(f"❌ 系统错误：{str(e)}")

    @accounting_command_group.command("查", aliases=["查看"], description="查看记账记录")
    async def cmd_list_records(self, event: AstrMessageEvent, count: Optional[str] = "10"):
        """
        查看记账记录
        :param count: 查看条数，默认10条
        """
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        
        if not records:
            yield event.plain_result("📒 暂无记账记录")
            return
            
        # 验证条数
        try:
            count_val = int(count)
            if count_val <= 0:
                count_val = 10
        except ValueError:
            count_val = 10
            
        # 按时间排序（最新在前）
        sorted_records = sorted(records, key=lambda x: x["timestamp"], reverse=True)[:count_val]
        
        # 构建输出
        output = f"📜 最近{len(sorted_records)}条记录（共{len(records)}条）：\n"
        for idx, rec in enumerate(sorted_records, 1):
            type_tag = "💵 收入" if rec["type"] == "income" else "💸 支出"
            type_info = f"来源：{rec['source']}" if rec["type"] == "income" else f"分类：{rec['category']}"
            
            output += (
                f"{idx}. {type_tag} | 金额：{rec['amount']}元\n"
                f"   {type_info} | 备注：{rec['note'] or '无'}\n"
                f"   时间：{rec['create_time']} | ID：{rec['id']}\n"
            )
            
        yield event.plain_result(output)

    @accounting_command_group.command("汇总", description="查看收支汇总")
    async def cmd_summary(self, event: AstrMessageEvent):
        """查看收支汇总统计"""
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        
        if not records:
            yield event.plain_result("📒 暂无记账记录")
            return
            
        # 计算汇总数据
        total_income = round(sum(r["amount"] for r in records if r["type"] == "income"), 2)
        total_expense = round(sum(r["amount"] for r in records if r["type"] == "expense"), 2)
        balance = round(total_income - total_expense, 2)
        
        # 计算记录数量
        income_count = sum(1 for r in records if r["type"] == "income")
        expense_count = sum(1 for r in records if r["type"] == "expense")
        
        output = (
            f"📊 收支汇总统计\n"
            f"====================\n"
            f"💵 总收入：{total_income}元（{income_count}条记录）\n"
            f"💸 总支出：{total_expense}元（{expense_count}条记录）\n"
            f"📈 当前结余：{balance}元\n"
            f"====================\n"
            f"提示：使用 /ac 查 查看详细记录"
        )
        yield event.plain_result(output)

    @accounting_command_group.command("删", aliases=["删除"], description="删除记账记录")
    async def cmd_delete_record(self, event: AstrMessageEvent, record_id: str):
        """
        删除指定ID的记账记录
        :param record_id: 记录ID
        """
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        
        for idx, rec in enumerate(records):
            if rec["id"] == record_id:
                # 删除记录
                deleted = records.pop(idx)
                self._save_data()
                
                type_str = "收入" if deleted["type"] == "income" else "支出"
                yield event.plain_result(
                    f"✅ 已成功删除{type_str}记录\n"
                    f"金额：{deleted['amount']}元\n"
                    f"ID：{record_id}"
                )
                return
                
        yield event.plain_result(f"❌ 未找到ID为「{record_id}」的记录\n请使用 /ac 查 确认记录ID")

    # ---------------------- AA分账命令 ----------------------
    @accounting_command_group.command("aa", description="AA分账功能")
    async def cmd_aa(self, event: AstrMessageEvent, *args):
        """
        AA分账功能主命令
        支持创建AA账单、对账和清账操作
        """
        user_id = event.get_sender_id()
        current_user = event.get_sender_name() or f"用户{user_id[:4]}"
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        
        # 操作1：查看AA账单（对账）
        if args and args[0] == "对账":
            async for res in self._aa_check(event):
                yield res
            return
            
        # 操作2：标记AA账单为已清账
        if len(args) >= 2 and args[0] == "清账":
            bill_id = args[1]
            async for res in self._aa_clear(event, bill_id, current_time):
                yield res
            return
            
        # 操作3：创建AA账单
        if len(args) < 2:
            yield event.plain_result(
                "❌ AA分账命令格式错误\n"
                "正确用法：\n"
                "1. 创建AA账单：/ac aa [参与人1] [参与人2] ... [总金额]\n"
                "   例：/ac aa 张三 李四 300\n"
                "2. 查看AA账单：/ac aa 对账\n"
                "3. 标记清账：/ac aa 清账 [账单ID]\n"
                "   例：/ac aa 清账 ab12"
            )
            return
            
        # 解析AA账单参数
        try:
            # 最后一个参数是金额
            amount_str = args[-1]
            participants = list(args[:-1])
            
            # 验证金额
            total_amount = float(amount_str)
            if total_amount <= 0:
                raise ValueError("AA金额必须大于0")
                
            # 处理参与人列表（去重并添加当前用户）
            participants = list(set(participants))  # 去重
            if current_user not in participants:
                participants.append(current_user)  # 确保创建者在参与人中
            total_people = len(participants)
            
            # 计算人均金额
            per_person = round(total_amount / total_people, 2)
            total_calculated = round(per_person * total_people, 2)
            diff = round(total_amount - total_calculated, 2)  # 分账误差
            
            # 生成账单ID
            bill_id = str(uuid.uuid4())[:4]  # 4位短ID
            
            # 创建AA账单记录
            aa_bill = {
                "id": bill_id,
                "total_amount": round(total_amount, 2),
                "per_person": per_person,
                "diff": diff,
                "payer": current_user,
                "participants": participants,
                "status": "待清账",  # 待清账/已清账
                "create_time": current_time,
                "clear_time": None
            }
            self.aa_bills.setdefault(user_id, []).append(aa_bill)
            
            # 创建对应的收支记录
            self._create_aa_records(user_id, current_user, current_time, 
                                   total_amount, per_person, participants, bill_id)
            
            # 保存数据
            self._save_data()
            
            # 返回结果
            result = (
                f"✅ AA账单创建成功\n"
                f"🆔 账单ID：{bill_id}\n"
                f"💵 总金额：{total_amount}元（{total_people}人平摊）\n"
                f"👥 参与人：{', '.join(participants)}\n"
                f"💸 每人应付：{per_person}元\n"
            )
            if diff != 0:
                result += f"⚠️ 分账误差：{diff}元（由你承担）\n"
            result += (
                f"⏰ 创建时间：{current_time}\n"
                f"操作提示：收到款项后执行 /ac aa 清账 {bill_id}"
            )
            yield event.plain_result(result)
            
        except ValueError as e:
            yield event.plain_result(f"❌ AA账单创建失败：{str(e)}")
        except Exception as e:
            logger.error(f"创建AA账单出错：{str(e)}")
            yield event.plain_result(f"❌ 系统错误：{str(e)}")

    # ---------------------- AA分账辅助方法 ----------------------
    async def _aa_check(self, event: AstrMessageEvent):
        """查看所有AA账单"""
        user_id = event.get_sender_id()
        bills = self.aa_bills.get(user_id, [])
        
        if not bills:
            yield event.plain_result("📋 暂无AA账单\n创建AA账单：/ac aa [参与人] [金额]")
            return
            
        # 按创建时间排序
        sorted_bills = sorted(bills, key=lambda x: x["create_time"], reverse=True)
        pending_bills = [b for b in sorted_bills if b["status"] == "待清账"]
        cleared_bills = [b for b in sorted_bills if b["status"] == "已清账"]
        
        # 构建输出
        output = "📊 AA账单对账\n"
        output += "========================================\n"
        
        # 待清账账单
        if pending_bills:
            output += f"🔴 待清账账单（{len(pending_bills)}条）\n"
            output += "----------------------------------------\n"
            for bill in pending_bills[:5]:  # 最多显示5条
                output += (
                    f"ID: {bill['id']} | 总金额: {bill['total_amount']}元\n"
                    f"参与人: {', '.join(bill['participants'])}\n"
                    f"每人应付: {bill['per_person']}元 | 创建时间: {bill['create_time']}\n"
                    f"操作: /ac aa 清账 {bill['id']}\n"
                    "----------------------------------------\n"
                )
        
        # 已清账账单
        if cleared_bills:
            output += f"🟢 已清账账单（{len(cleared_bills)}条）\n"
            output += "----------------------------------------\n"
            for bill in cleared_bills[:3]:  # 最多显示3条
                output += (
                    f"ID: {bill['id']} | 总金额: {bill['total_amount']}元\n"
                    f"参与人: {', '.join(bill['participants'])}\n"
                    f"清账时间: {bill['clear_time']}\n"
                    "----------------------------------------\n"
                )
        
        output += f"📝 总计：共{len(sorted_bills)}条AA账单"
        yield event.plain_result(output)

    async def _aa_clear(self, event: AstrMessageEvent, bill_id: str, clear_time: str):
        """标记AA账单为已清账"""
        user_id = event.get_sender_id()
        bills = self.aa_bills.get(user_id, [])
        
        for bill in bills:
            if bill["id"] == bill_id:
                if bill["status"] == "已清账":
                    yield event.plain_result(
                        f"✅ 账单「{bill_id}」已是已清账状态\n"
                        f"清账时间：{bill['clear_time']}"
                    )
                    return
                    
                # 更新账单状态
                bill["status"] = "已清账"
                bill["clear_time"] = clear_time
                self._save_data()
                
                yield event.plain_result(
                    f"✅ 账单「{bill_id}」已标记为清账\n"
                    f"金额: {bill['total_amount']}元\n"
                    f"参与人: {', '.join(bill['participants'])}\n"
                    f"清账时间: {clear_time}"
                )
                return
                
        yield event.plain_result(
            f"❌ 未找到ID为「{bill_id}」的AA账单\n"
            f"请使用 /ac aa 对账 查看所有账单ID"
        )

    def _create_aa_records(self, user_id: str, payer: str, create_time: str,
                          total_amount: float, per_person: float, 
                          participants: List[str], bill_id: str):
        """创建AA分账对应的收支记录"""
        timestamp = int(time.time())
        
        # 1. 创建付款人的支出记录
        expense_id = str(uuid.uuid4())[:8]
        expense_record = {
            "id": expense_id,
            "type": "expense",
            "amount": total_amount,
            "category": "AA制支出",
            "note": f"AA账单-{bill_id}-{', '.join(participants)}",
            "create_time": create_time,
            "timestamp": timestamp,
            "aa_bill_id": bill_id
        }
        self.user_records.setdefault(user_id, []).append(expense_record)
        
        # 2. 创建其他参与人的应收收入记录
        for person in participants:
            if person == payer:
                continue  # 跳过付款人自己
                
            income_id = str(uuid.uuid4())[:8]
            income_record = {
                "id": income_id,
                "type": "income",
                "amount": per_person,
                "source": "AA制应收",
                "note": f"AA账单-{bill_id}-来自{person}",
                "create_time": create_time,
                "timestamp": timestamp,
                "aa_bill_id": bill_id
            }
            self.user_records.setdefault(user_id, []).append(income_record)

    # ---------------------- 数据存储与加载（遵循AstrBot数据管理规范） ----------------------
    def _load_data(self):
        """加载插件数据"""
        try:
            # 加载记账记录
            if os.path.exists(self.acc_data_path):
                with open(self.acc_data_path, "r", encoding="utf-8") as f:
                    self.user_records = json.load(f)
            
            # 加载AA账单
            if os.path.exists(self.aa_data_path):
                with open(self.aa_data_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
                    
            logger.info("插件数据加载成功")
            
        except Exception as e:
            logger.error(f"数据加载失败：{str(e)}，将使用空数据")
            self.user_records = {}
            self.aa_bills = {}

    def _save_data(self):
        """保存插件数据"""
        try:
            # 保存记账记录
            with open(self.acc_data_path, "w", encoding="utf-8") as f:
                json.dump(self.user_records, f, ensure_ascii=False, indent=2)
            
            # 保存AA账单
            with open(self.aa_data_path, "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
                
            logger.debug("插件数据保存成功")
            
        except Exception as e:
            logger.error(f"数据保存失败：{str(e)}")
