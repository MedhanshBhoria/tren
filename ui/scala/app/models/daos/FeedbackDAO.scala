package models.daos

import models.{Feedback, SQLTables}
import play.api.Configuration
import play.api.db.slick.{DatabaseConfigProvider, HasDatabaseConfigProvider}
import play.db.NamedDatabase
import slick.jdbc.{JdbcProfile, PostgresProfile, SQLiteProfile}

import javax.inject.{Inject, Singleton}
import scala.concurrent.{ExecutionContext, Future}

@Singleton
class FeedbackDAO @Inject()(@NamedDatabase("ragmeup") protected val dbConfigProvider: DatabaseConfigProvider, sqlTables: SQLTables)
                       (implicit ec: ExecutionContext, config: Configuration) extends HasDatabaseConfigProvider[JdbcProfile] {

  val selectedProfile: JdbcProfile = config.get[String]("slick.dbs.ragmeup.profile") match {
    case "slick.jdbc.SQLiteProfile$" => SQLiteProfile
    case "slick.jdbc.PostgresProfile$" => PostgresProfile
    case other =>
      throw new IllegalArgumentException(s"Unsupported database profile: $other")
  }

  import selectedProfile.api._
  import sqlTables._

  def add(feedback: Feedback): Future[Int] = db.run(Feedbacks += feedback)
}
