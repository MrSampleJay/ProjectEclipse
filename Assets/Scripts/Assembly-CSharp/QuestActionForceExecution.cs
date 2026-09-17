using System.Xml;

public class QuestActionForceExecution : QuestAction
{
	private string Name;

	public override void Parse(XmlNode EPKLCPOEELO)
	{
		base.Parse(EPKLCPOEELO);
		Name = EPKLCPOEELO.Attributes["Name"].CIPOICEEIBK(string.Empty);
	}

	public override void DEJMHFMLKIC(QuestParameters GFIHPBCEEOB)
	{
		base.DEJMHFMLKIC(GFIHPBCEEOB);
		ListSF.GetInstance().AddQuestToStek(Name, true);
		OGIJONMKABB();
	}
}
