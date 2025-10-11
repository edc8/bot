from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import At, Plain, Image, MessageChain
from datetime import datetime
import asyncio
from typing import Dict, List, Optional, Tuple

# 账单数据结构定义
class AABill:
    def __init__(self, bill_id: str, creator_id: str, creator_name: str, title: str):
        self.bill_id = bill_id  # 账单唯一ID（时间戳+创建者ID前4位）
        self.creator_id = creator_id  # 创建者ID
        self.creator_name = creator_name  # 创建者昵称
        self.title = title  # 账单标题（如“周末聚餐”）
        self.create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 创建时间
        self.items: List[Dict] = []  # 消费项列表，每个元素含name/amount/payer_id/payer_name
        self.members: Dict[str, str] = {}  # 参与人列表（ID: 昵称）
        self.total_amount: float = 0.0  # 总金额
        self.settled: bool = False  # 是否已结算

    def add_item(self, name: str, amount: float, payer_id: str, payer_name: str) -> bool:
        """添加消费项，自动更新总金额和参与人"""
        if self.settled:
            return False  # 已结算账单不可修改
        # 校验金额合法性
        if amount <= 0:
            return False
        # 添加消费项
        self.items.append({
            "name": name,
            "amount": round(amount, 2),
            "payer_id": payer_id,
            "payer_name": payer_name
        })
        # 更新总金额
        self.total_amount = round(self.total_amount + amount, 2)
        # 添加付款人到参与人列表
        self.members[payer_id] = payer_name
        return True

    def add_member(self, member_id: str, member_name: str) -> bool:
        """手动添加参与人（非付款人）"""
        if self.settled:
            return False
        if member_id not in self.members:
            self.members[member_id] = member_name
            return True
        return False  # 已存在该成员

    def calculate_dues(self) -> Dict[str, Tuple[float, float]]:
        """计算每个人的应付金额和收支差额
        返回格式：{成员ID: (应付金额, 收支差额)}
        收支差额 = 已付款金额 - 应付金额（正数为应收回，负数为应支付）
        """
        if not self.members:
            return {}
        
        # 1. 计算每人已付款总金额
        payer_summary: Dict[str, float] = {}
        for item in self.items:
            payer_id = item["payer_id"]
            amount = item["amount"]
            payer_summary[payer_id] = round(payer_summary.get(payer_id, 0.0) + amount, 2)
        
        # 2. 计算每人应付金额（总金额 / 参与人数，保留2位小数）
        member_count = len(self.members)
        per_person_dues = round(self.total_amount / member_count, 2) if member_count > 0 else 0.0
        
        # 3. 计算收支差额
        result = {}
        for member_id, member_name in self.members.items():
            paid = payer_summary.get(member_id, 0.0)
            dues = per_person_dues
            balance = round(paid - dues, 2)  # 差额：正=应收回，负=应支付
            result[member_id] = (dues, balance)
        
        return result

    def mark_settled(self) -> bool:
        """标记账单为已结算"""
        if not self.items:
            return False  # 空账单不可结算
        self.settled = True
        return True

    def to_text(self) -> str:
        """将账单信息转为文本格式，用于展示"""
        # 基础信息
        text = f"📊 【AA账单】{self.title}\n"
        text += f"编号：{self.bill_id}\n"
        text += f"创建者：{self.creator_name}（{self.create_time}）\n"
        text += f"状态：{'✅ 已结算' if self.settled else '🔄 待结算'}\n"
        text += f"总金额：¥{self.total_amount:.2f} | 参与人数：{len(self.members)}人\n\n"
        
        # 消费项列表
        if self.items:
            text += "📝 消费项：\n"
            for idx, item in enumerate(self.items, 1):
                text += f"  {idx}. {item['name']} - ¥{item['amount']:.2f}（付款人：{item['payer_name']}）\n"
        else:
            text += "📝 消费项：暂无\n"
        
        # 参与人列表
        if self.members:
            text += "\n👥 参与人：\n"
            members_str = "、".join([name for name in self.members.values()])
            text += f"  {members_str}\n"
        
        # 计算结果（仅待结算账单展示）
        if not self.settled and self.items and self.members:
            text += "\n💸 分账计算：\n"
            dues_data = self.calculate_dues()
            for member_id, (dues, balance) in dues_data.items():
                member_name = self.members[member_id]
                if balance > 0:
                    text += f"  {member_name}：应付¥{dues:.2f} | 多付¥{balance:.2f}（应收回）\n"
                elif balance < 0:
                    text += f"  {member_name}：应付¥{dues:.2f} | 少付¥{abs(balance):.2f}（应支付）\n"
                else:
                    text += f"  {member_name}：应付¥{dues:.2f} | 刚好付清\n"
        
        return text


@register(
    plugin_name="astrbot_plugin_aa_split",  # 插件名（必须以astrbot_plugin_开头）
    author="YourName",  # 替换为你的名字/昵称
    description="AA制分账插件，支持创建账单、添加消费项、自动计算每个人应付金额",
    version="1.0.0",
    repo_url="https://github.com/YourRepo/astrbot_plugin_aa_split"  # 替换为你的仓库地址（可选）
)
class AASplitPlugin(Star):
    def __init__(self, context: Context, config: Optional[AstrBotConfig] = None):
        super().__init__(context)
        self.config = config  # 插件配置（如后续需扩展自定义配置可使用）
        self.bills: Dict[str, AABill] = {}  # 账单存储（bill_id: AABill对象）
        self.session_data: Dict[str, str] = {}  # 会话临时数据（用于多轮交互，如创建账单）
        logger.info("AA制分账插件初始化完成，已准备就绪！")

    async def initialize(self):
        """插件异步初始化（如加载历史账单，此处暂用内存存储，实际可扩展文件/数据库存储）"""
        # 如需持久化，可在此处读取本地文件（如JSON）加载历史账单
        pass

    # ------------------------------ 核心指令组：/aa ------------------------------
    @filter.command_group("aa", alias={"aasplit", "分账"})
    async def aa_group(self, event: AstrMessageEvent):
        """AA制分账主指令组，所有分账功能通过该指令触发
        可用子指令：create（创建账单）、add（添加消费）、member（添加参与人）、calc（计算分账）、list（账单列表）、settle（标记结算）
        """
        pass

    # 1. 子指令：创建账单（/aa create 账单标题）
    @aa_group.command("create", alias={"新建", "创建"})
    async def aa_create(self, event: AstrMessageEvent, title: str):
        """创建新的AA账单
        用法：/aa create 周末聚餐（或 /分账 新建 团建费用）
        """
        # 生成账单唯一ID（时间戳+创建者ID前4位，避免重复）
        timestamp = datetime.now().timestamp()
        creator_id = event.get_sender_id()
        bill_id = f"AA{int(timestamp)}_{creator_id[:4]}"
        
        # 创建账单对象
        creator_name = event.get_sender_name()
        new_bill = AABill(
            bill_id=bill_id,
            creator_id=creator_id,
            creator_name=creator_name,
            title=title
        )
        
        # 添加创建者为默认参与人
        new_bill.add_member(creator_id, creator_name)
        
        # 存储账单
        self.bills[bill_id] = new_bill
        
        # 回复结果
        reply_text = f"✅ 成功创建AA账单！\n"
        reply_text += f"编号：{bill_id}\n"
        reply_text += f"标题：{title}\n"
        reply_text += f"\n下一步操作：\n"
        reply_text += f"1. 添加消费项：/aa add {bill_id} 火锅 300（付款人默认是你）\n"
        reply_text += f"2. 添加参与人：/aa member {bill_id} @好友（或指定ID）\n"
        reply_text += f"3. 查看账单：/aa list {bill_id}"
        
        yield event.plain_result(reply_text)
        logger.info(f"用户{creator_name}({creator_id})创建AA账单：{bill_id}_{title}")

    # 2. 子指令：添加消费项（/aa add 账单ID 消费名称 金额 [付款人ID/@付款人]）
    @aa_group.command("add", alias={"添加消费", "加项"})
    async def aa_add_item(self, event: AstrMessageEvent, bill_id: str, item_name: str, amount: float, payer: Optional[str] = None):
        """添加消费项到指定账单
        用法1（自己付款）：/aa add AA123456_1234 火锅 300
        用法2（指定他人付款）：/aa add AA123456_1234 奶茶 50 @好友（或好友ID）
        """
        # 1. 校验账单是否存在
        if bill_id not in self.bills:
            yield event.plain_result(f"❌ 未找到编号为【{bill_id}】的账单，请检查编号是否正确！")
            return
        
        bill = self.bills[bill_id]
        
        # 2. 校验账单状态（已结算不可修改）
        if bill.settled:
            yield event.plain_result(f"❌ 账单【{bill_id}】已结算，不可添加新消费项！")
            return
        
        # 3. 确定付款人信息
        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()
        
        if not payer:
            # 未指定付款人，默认是指令发送者
            payer_id = sender_id
            payer_name = sender_name
        else:
            # 处理@付款人（优先识别@消息段）
            at_components = [comp for comp in event.get_messages() if comp.type == "At"]
            if at_components:
                payer_id = at_components[0].qq  # QQ平台At组件的用户ID字段
                payer_name = at_components[0].name or f"用户{payer_id[:4]}"
            else:
                # 手动指定付款人ID
                payer_id = payer
                payer_name = f"用户{payer_id[:4]}"  # 若无法获取昵称，用ID前4位代替
        
        # 4. 添加消费项
        success = bill.add_item(
            name=item_name,
            amount=amount,
            payer_id=payer_id,
            payer_name=payer_name
        )
        
        if not success:
            yield event.plain_result(f"❌ 消费项添加失败！请确保金额为正数（当前金额：{amount}）")
            return
        
        # 5. 回复结果
        reply_text = f"✅ 成功添加消费项到账单【{bill.title}】（{bill_id}）\n"
        reply_text += f"消费项：{item_name} - ¥{amount:.2f}\n"
        reply_text += f"付款人：{payer_name}\n"
        reply_text += f"当前总金额：¥{bill.total_amount:.2f} | 参与人数：{len(bill.members)}人\n"
        reply_text += f"\n提示：可继续添加消费项，或用 /aa calc {bill_id} 查看分账结果"
        
        yield event.plain_result(reply_text)
        logger.info(f"账单{bill_id}添加消费项：{item_name}(¥{amount})，付款人：{payer_name}")

    # 3. 子指令：添加参与人（/aa member 账单ID @成员1 @成员2 或 /aa member 账单ID 成员ID 成员昵称）
    @aa_group.command("member", alias={"添加成员", "加人"})
    async def aa_add_member(self, event: AstrMessageEvent, bill_id: str, *members: str):
        """添加参与人到指定账单（支持@多个成员或手动输入ID+昵称）
        用法1（@成员）：/aa member AA123456_1234 @好友1 @好友2
        用法2（手动输入）：/aa member AA123456_1234 123456 小明 654321 小红
        """
        # 1. 校验账单
        if bill_id not in self.bills:
            yield event.plain_result(f"❌ 未找到编号为【{bill_id}】的账单！")
            return
        
        bill = self.bills[bill_id]
        if bill.settled:
            yield event.plain_result(f"❌ 账单【{bill_id}】已结算，不可添加参与人！")
            return
        
        # 2. 解析参与人（优先处理@消息段）
        added_count = 0
        failed_list = []
        
        # 先处理消息中的@组件（无需在指令参数中显式输入）
        at_components = [comp for comp in event.get_messages() if comp.type == "At"]
        for at_comp in at_components:
            member_id = at_comp.qq
            member_name = at_comp.name or f"用户{member_id[:4]}"
            if bill.add_member(member_id, member_name):
                added_count += 1
            else:
                failed_list.append(f"{member_name}（已存在）")
        
        # 再处理指令参数中的手动输入成员（需成对输入：ID 昵称）
        if len(members) % 2 == 0:
            for i in range(0, len(members), 2):
                member_id = members[i]
                member_name = members[i+1]
                if bill.add_member(member_id, member_name):
                    added_count += 1
                else:
                    failed_list.append(f"{member_name}（已存在）")
        elif members:
            # 手动输入参数数量不对（非成对）
            failed_list.append("手动输入格式错误（需成对输入：成员ID 成员昵称）")
        
        # 3. 回复结果
        reply_text = f"✅ 参与人添加完成（账单：{bill.title} - {bill_id}）\n"
        reply_text += f"成功添加：{added_count}人\n"
        if failed_list:
            reply_text += f"添加失败：{'; '.join(failed_list)}\n"
        reply_text += f"当前参与人总数：{len(bill.members)}人\n"
        reply_text += f"参与人列表：{', '.join(bill.members.values())}"
        
        yield event.plain_result(reply_text)
        logger.info(f"账单{bill_id}添加参与人：成功{added_count}人，失败{len(failed_list)}项")

    # 4. 子指令：计算分账（/aa calc 账单ID）
    @aa_group.command("calc", alias={"计算", "分账结果"})
    async def aa_calculate(self, event: AstrMessageEvent, bill_id: str):
        """计算指定账单的分账结果，展示每个人应付金额和收支差额
        用法：/aa calc AA123456_1234（或 /分账 计算 AA123456_1234）
        """
        # 1. 校验账单
        if bill_id not in self.bills:
            yield event.plain_result(f"❌ 未找到编号为【{bill_id}】的账单！")
            return
        
        bill = self.bills[bill_id]
        
        # 2. 校验账单数据（需有消费项和参与人）
        if not bill.items:
            yield event.plain_result(f"❌ 账单【{bill_id}】暂无消费项，请先添加消费（/aa add 账单ID 消费名 金额）！")
            return
        
        if len(bill.members) < 2:
            yield event.plain_result(f"❌ 账单【{bill_id}】参与人不足2人（当前{len(bill.members)}人），无法进行AA分账！")
            return
        
        # 3. 生成分账结果文本
        result_text = bill.to_text()
        result_text += "\n📌 分账建议：\n"
        result_text += "  - 收支差额为正数的成员：可收回对应金额\n"
        result_text += "  - 收支差额为负数的成员：需支付对应金额\n"
        result_text += f"  - 结算后请标记：/aa settle {bill_id}"
        
        # 4. 发送结果（支持长文本，若超过平台限制可自动转为图片）
        # 此处先尝试纯文本发送，如需文转图可扩展text_to_image方法
        yield event.plain_result(result_text)
        logger.info(f"用户{event.get_sender_name()}查看账单{bill_id}分账结果")

    # 5. 子指令：账单列表（/aa list [账单ID]）
    @aa_group.command("list", alias={"列表", "查看账单"})
    async def aa_list(self, event: AstrMessageEvent, bill_id: Optional[str] = None):
        """查看所有账单或指定账单详情
        用法1（所有账单）：/aa list（或 /分账 列表）
        用法2（指定账单）：/aa list AA123456_1234
        """
        if bill_id:
            # 查看指定账单详情
            if bill_id not in self.bills:
                yield event.plain_result(f"❌ 未找到编号为【{bill_id}】的账单！")
                return
            bill_text = self.bills[bill_id].to_text()
            yield event.plain_result(bill_text)
        else:
            # 查看所有账单（按创建时间倒序）
            if not self.bills:
                yield event.plain_result("📭 当前暂无AA账单，可通过 /aa create 标题 创建新账单！")
                return
            
            # 按创建时间排序（新账单在前）
            sorted_bills = sorted(self.bills.values(), key=lambda x: x.create_time, reverse=True)
            
            # 生成列表文本
            list_text = "📊 所有AA账单列表（共{len(sorted_bills)}个）：\n\n"
            for idx, bill in enumerate(sorted_bills, 1):
                list_text += f"{idx}. 【{bill.title}】\n"
                list_text += f"   编号：{bill.bill_id}\n"
                list_text += f"   状态：{'✅ 已结算' if bill.settled else '🔄 待结算'}\n"
                list_text += f"   总金额：¥{bill.total_amount:.2f} | 参与人：{len(bill.members)}人\n"
                list_text += f"   创建者：{bill.creator_name}（{bill.create_time}）\n\n"
            
            list_text += "📌 操作提示：\n"
            list_text += "  - 查看详情：/aa list 账单编号\n"
            list_text += "  - 计算分账：/aa calc 账单编号\n"
            list_text += "  - 标记结算：/aa settle 账单编号"
            
            yield event.plain_result(list_text)
        
        logger.info(f"用户{event.get_sender_name()}查看AA账单列表（指定账单：{bill_id if bill_id else '无'}）")

    # 6. 子指令：标记结算（/aa settle 账单ID）
    @aa_group.command("settle", alias={"结算", "完成"})
    async def aa_settle(self, event: AstrMessageEvent, bill_id: str):
        """标记账单为已结算（仅创建者可操作）
        用法：/aa settle AA123456_1234（或 /分账 结算 AA123456_1234）
        """
        # 1. 校验账单
        if bill_id not in self.bills:
            yield event.plain_result(f"❌ 未找到编号为【{bill_id}】的账单！")
            return
        
        bill = self.bills[bill_id]
        sender_id = event.get_sender_id()
        
        # 2. 校验权限（仅创建者可标记结算）
        if bill.creator_id != sender_id:
            yield event.plain_result(f"❌ 无权限操作！仅账单创建者（{bill.creator_name}）可标记结算！")
            return
        
        # 3. 标记结算
        if bill.settled:
            yield event.plain_result(f"✅ 账单【{bill_id}】已处于结算状态，无需重复操作！")
            return
        
        success = bill.mark_settled()
        if not success:
            yield event.plain_result(f"❌ 账单【{bill_id}】暂无消费项，无法标记结算！")
            return
        
        # 4. 回复结果
        reply_text = f"✅ 成功标记账单【{bill.title}】（{bill_id}）为已结算！\n"
        reply_text += "📌 结算后账单不可再修改，如需新分账请创建新账单（/aa create 标题）"
        
        yield event.plain_result(reply_text)
        logger.info(f"账单创建者{bill.creator_name}标记账单{bill_id}为已结算")

    # ------------------------------ 辅助功能：帮助指令 ------------------------------
    @filter.command("aahelp", alias={"分账帮助", "aa帮助"})
    async def aa_help(self, event: AstrMessageEvent):
        """查看AA分账插件的所有功能和用法
        用法：/aahelp（或 /分账帮助）
        """
        help_text = "📚 AA制分账插件使用帮助\n"
        help_text += "=======================\n"
        help_text += "【核心指令组：/aa 或 /分账】\n\n"
        help_text += "1. 创建账单\n"
        help_text += "   用法：/aa create 账单标题（如 /aa create 周末聚餐）\n"
        help_text += "   功能：创建新的AA账单，自动添加创建者为参与人\n\n"
        help_text += "2. 添加消费项\n"
        help_text += "   用法1：/aa add 账单ID 消费名 金额（自己付款）\n"
        help_text += "   用法2：/aa add 账单ID 消费名 金额 @付款人（他人付款）\n"
        help_text += "   示例：/aa add AA1234 火锅 300 @小明\n\n"
        help_text += "3. 添加参与人\n"
        help_text += "   用法1：/aa member 账单ID @好友1 @好友2（@方式）\n"
        help_text += "   用法2：/aa member 账单ID 123456 小明（ID+昵称）\n"
        help_text += "   功能：添加非付款人参与分账\n\n"
        help_text += "4. 计算分账\n"
        help_text += "   用法：/aa calc 账单ID（如 /aa calc AA1234）\n"
        help_text += "   功能：自动计算每个人应付金额和收支差额\n\n"
        help_text += "5. 查看账单\n"
        help_text += "   用法1：/aa list（查看所有账单）\n"
        help_text += "   用法2：/aa list 账单ID（查看指定账单详情）\n\n"
        help_text += "6. 标记结算\n"
        help_text += "   用法：/aa settle 账单ID（如 /aa settle AA1234）\n"
        help_text += "   说明：仅账单创建者可操作，结算后不可修改\n\n"
        help_text += "【其他指令】\n"
        help_text += "   /aahelp 或 /分账帮助：查看本帮助文档\n"
        
        yield event.plain_result(help_text)
        logger.info(f"用户{event.get_sender_name()}查看AA分账插件帮助")

    async def terminate(self):
        """插件卸载时执行（如保存账单数据到本地）"""
        # 此处可扩展持久化逻辑（如将账单保存为JSON文件）
        if self.bills:
            bill_count = len(self.bills)
            logger.info(f"AA制分账插件正在卸载，当前有{bill_count}个账单（可扩展持久化存储）")
        else:
            logger.info("AA制分账插件正在卸载，无历史账单")
